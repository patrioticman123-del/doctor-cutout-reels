import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave
import math

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import audio
import render
from visuals import Stage, chunks, find_font
import imageio_ffmpeg


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.episode=json.loads((ROOT/"examples/template.json").read_text(encoding="utf-8"))

    def test_medical_claim_requires_known_evidence(self):
        self.episode["content_type"]="medical"
        with self.assertRaises(ValueError):
            render.validate(self.episode)
        self.episode["sources"]=[{"id":"official","title":"Source fixture","url":"https://example.org/",
                                  "accessed":"2026-11-21","supports":"Test fixture only"}]
        self.episode["scenes"][0]["claims"]=["unknown"]
        with self.assertRaises(ValueError):
            render.validate(self.episode)
        self.episode["scenes"][0]["claims"]=["official"]
        self.assertEqual(render.validate(self.episode)["content_type"],"medical")

    def test_subtitle_chunks_preserve_every_qualifier(self):
        text="部分患者可能出現不同反應，仍需依個別情況評估。"*8
        pieces=chunks(text)
        self.assertEqual("".join(pieces),text)
        self.assertTrue(all(len(p)<=27 for p in pieces))

    def test_silent_speech_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"silent.wav"
            audio.write_wav(path,[0]*2400)
            with self.assertRaises(ValueError):
                audio.read_wav(path)

    def test_audio_cache_tracks_source_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            cache=base/"cache"
            cache.mkdir()
            source=base/"voice.wav"
            scene=dict(self.episode["scenes"][0],audio="voice.wav")
            ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
            audio.write_wav(source,[800]*2400)
            first=audio.speech(scene,self.episode,"files",base,cache,ffmpeg)
            audio.write_wav(source,[1600]*2400)
            second=audio.speech(scene,self.episode,"files",base,cache,ffmpeg)
            self.assertGreater(max(second),max(first))
            self.assertEqual(len(list(cache.glob("*.wav"))),2)

    def test_default_cli_is_draft_only_and_stale_approval_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            episode=base/"episode.json"
            episode.write_text(json.dumps(self.episode,ensure_ascii=False),encoding="utf-8")
            output=base/"draft"
            command=[sys.executable,str(ROOT/"scripts/render.py"),str(episode),"--out",str(output)]
            result=subprocess.run(command,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
            manifest=json.loads((output/"draft.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"],"awaiting_user_review")
            self.assertTrue((output/"script.md").is_file())
            self.assertEqual(len(list((output/"frames").glob("*.jpg"))),len(self.episode["scenes"]))
            self.assertFalse((output/"audio").exists())
            self.assertFalse(list(output.glob("*.wav")))
            self.assertFalse(list(output.glob("*.mp4")))
            self.episode["scenes"][0]["text"]+="這是修改。"
            episode.write_text(json.dumps(self.episode,ensure_ascii=False),encoding="utf-8")
            result=subprocess.run(command+["--render","--approved-hash",manifest["revision"]],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((output/"audio").exists())

    def test_same_actor_size_for_all_speakers_and_three_person_shot(self):
        data=render.validate(self.episode)
        stage=Stage(ROOT/"assets",data,find_font())
        seen=[]
        original=stage.character_sprite
        def capture(name,height,mouth,blink):
            sprite=original(name,height,mouth,blink)
            seen.append((name,sprite.size))
            return sprite
        stage.character_sprite=capture
        scenes=data["scenes"]+[dict(data["scenes"][0],cast=["doctor","mei","alo"],teaching={"mode":"dialogue"})]
        for i,scene in enumerate(scenes):
            item=dict(scene,index=i,start=0,end=5,voice_start=.18,voice_end=4.5,envelope=[0]*120)
            frame=stage.frame(item,2,24)
            self.assertEqual(frame.size,(1080,1920))
        self.assertEqual({size for _,size in seen},{(520,780)})

    def test_teaching_material_is_visible_in_draft_and_invalidates_approval(self):
        data=render.validate(self.episode)
        stage=Stage(ROOT/"assets",data,find_font())
        scene=copy.deepcopy(next(s for s in data["scenes"] if s["teaching"]["mode"]=="bone_model"))
        scene.update(index=90,start=0,end=5,voice_start=.18,voice_end=4.5,envelope=[0]*120)
        with_model=stage.frame(scene,2,24)
        # Compare the actual center prop region against the identical scene with no lesson.
        plain=dict(scene,index=91,teaching={"mode":"dialogue"})
        no_model=stage.frame(plain,2,24)
        from PIL import ImageChops
        diff=ImageChops.difference(with_model.crop((400,820,680,1180)),
                                   no_model.crop((400,820,680,1180)))
        self.assertIsNotNone(diff.getbbox())
        before=render.revision(data)
        board=next(s for s in data["scenes"] if s["teaching"]["mode"]=="blackboard")
        board["teaching"]["points"][0]="修訂後的重點"
        self.assertNotEqual(render.revision(data),before)
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            render.draft(data,output,find_font())
            self.assertIn("修訂後的重點",(output/"script.md").read_text(encoding="utf-8"))
            self.assertFalse(list(output.glob("*.mp4")))
            self.assertFalse((output/"audio").exists())

    def test_teaching_props_reject_obscured_layout_and_unknown_modes(self):
        data=render.validate(self.episode)
        scene=next(s for s in data["scenes"] if s["teaching"]["mode"]=="bone_model")
        scene["cast"]=["doctor","mei","alo"]
        with self.assertRaises(ValueError):
            render.validate(data)
        scene["cast"]=["doctor","alo"]
        scene["teaching"]["mode"]="unknown"
        with self.assertRaises(ValueError):
            render.validate(data)

    def test_files_backend_renders_decodable_av_with_measured_timing(self):
        # Synthetic tones are isolated fixtures, never presented as real speech.
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            audio.write_wav(base/"fixture.wav",(1400*math.sin(i*2*math.pi*220/audio.RATE)
                                               for i in range(16*audio.RATE)))
            episode=copy.deepcopy(self.episode)
            episode["scenes"]=episode["scenes"][:2]
            for scene in episode["scenes"]:
                scene["audio"]="fixture.wav"
            data=render.validate(episode)
            output=base/"output"
            manifest=render.render(data,base,output,"files",180,1,find_font())
            self.assertTrue(30<=manifest["duration"]<=60)
            self.assertEqual(manifest["timeline"][1]["start"],manifest["timeline"][0]["end"])
            self.assertAlmostEqual(manifest["timeline"][0]["voice_end"]-
                                   manifest["timeline"][0]["voice_start"],16,places=3)
            result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),"-v","info","-i",str(output/"episode.mp4"),
                                   "-map","0:v:0","-map","0:a:0","-f","null","-"],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
            self.assertIn(b"180x320",result.stderr)
            self.assertIn(b"Audio: aac",result.stderr)
            self.assertGreater((output/"episode.srt").stat().st_size,50)
            with wave.open(str(output/"mix.wav"),"rb") as mix:
                self.assertAlmostEqual(mix.getnframes()/mix.getframerate(),manifest["duration"],places=3)


if __name__=="__main__":
    unittest.main()
