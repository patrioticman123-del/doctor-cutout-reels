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

    def test_brisk_audio_trims_edges_preserves_pitch_and_refreshes_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            cache=base/"cache"
            cache.mkdir()
            tone=[int(6000*math.sin(i*2*math.pi*220/audio.RATE)) for i in range(2*audio.RATE)]
            audio.write_wav(base/"voice.wav",[0]*(audio.RATE//4)+tone+[0]*(audio.RATE//4))
            scene=dict(self.episode["scenes"][0],audio="voice.wav")
            ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
            episode=copy.deepcopy(self.episode)
            episode["pacing"]={"speech_speed":1.0,"lead_in":.03,"trim_silence":False}
            original=audio.speech(scene,episode,"files",base,cache,ffmpeg)
            self.assertAlmostEqual(len(original)/audio.RATE,2.5,places=3)
            episode["pacing"]={"speech_speed":1.08,"lead_in":.03,"trim_silence":True}
            brisk=audio.speech(scene,episode,"files",base,cache,ffmpeg)
            self.assertTrue(1.84<len(brisk)/audio.RATE<1.97)
            middle=brisk[audio.RATE//10:-audio.RATE//10]
            positive_crossings=sum(a<=0<b for a,b in zip(middle,middle[1:]))
            frequency=positive_crossings/(len(middle)/audio.RATE)
            self.assertAlmostEqual(frequency,220,delta=4)
            episode["pacing"]["speech_speed"]=1.16
            faster=audio.speech(scene,episode,"files",base,cache,ffmpeg)
            self.assertLess(len(faster),len(brisk))
            self.assertEqual(len(list(cache.glob("*.wav"))),3)

    def test_brisk_assembly_uses_short_gaps_and_keeps_utterances_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            audio.write_wav(base/"voice.wav",(5000*math.sin(i*2*math.pi*220/audio.RATE)
                                              for i in range(audio.RATE)))
            episode=copy.deepcopy(self.episode)
            episode["scenes"]=episode["scenes"][:2]
            for scene in episode["scenes"]:
                scene.update(audio="voice.wav",hold=.1)
            timeline,duration=audio.assemble(episode,"files",base,base,imageio_ffmpeg.get_ffmpeg_exe(),24)
            gap=timeline[1]["voice_start"]-timeline[0]["voice_end"]
            self.assertTrue(.13<=gap<.18)
            self.assertGreaterEqual(timeline[1]["voice_start"],timeline[0]["voice_end"])
            self.assertAlmostEqual(timeline[0]["voice_start"],.03)
            self.assertGreaterEqual(duration,timeline[-1]["voice_end"])

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
            self.episode["scenes"][0]["text"]+="這樣也可以嗎？"
            episode.write_text(json.dumps(self.episode,ensure_ascii=False),encoding="utf-8")
            result=subprocess.run(command+["--render","--approved-hash",manifest["revision"]],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b"Missing/stale approval hash",result.stderr)
            self.assertFalse((output/"audio").exists())

    def test_question_dialogue_and_medical_closing_require_explicit_structure(self):
        data=copy.deepcopy(self.episode)
        first=data["scenes"][0]
        first["intent"]="question"
        first["text"]="如果從足部開始看呢。"
        with self.assertRaises(ValueError):
            render.validate(data)
        first["text"]="如果從足部開始看呢？"
        self.assertEqual(render.validate(data)["scenes"][0]["intent"],"question")
        data["content_type"]="medical"
        data["sources"]=[{"id":"source","title":"Source fixture","url":"https://example.org/",
                          "accessed":"2026-11-22","supports":"Test fixture only"}]
        first["claims"]=["source"]
        self.assertEqual(render.validate(data)["scenes"][-1]["intent"],"closing")
        data["scenes"][-1]["intent"]="reaction"
        with self.assertRaises(ValueError):
            render.validate(data)
        data["scenes"][-1]["intent"]="closing"
        data["scenes"][-1]["speaker"]="alo"
        with self.assertRaises(ValueError):
            render.validate(data)

    def test_same_actor_size_for_all_speakers_and_three_person_shot(self):
        data=render.validate(self.episode)
        stage=Stage(ROOT/"assets",data,find_font())
        seen=[]
        original=stage.character_sprite
        def capture(name,height,mouth,blink,**pose):
            sprite=original(name,height,mouth,blink,**pose)
            seen.append((name,sprite.size))
            return sprite
        stage.character_sprite=capture
        scenes=data["scenes"]+[dict(data["scenes"][0],cast=["doctor","mei","alo"],teaching={"mode":"dialogue"})]
        for i,scene in enumerate(scenes):
            item=dict(scene,index=i,start=0,end=5,voice_start=.18,voice_end=4.5,envelope=[0]*120)
            frame=stage.frame(item,2,24)
            self.assertEqual(frame.size,(1080,1920))
        self.assertEqual({size[1] for _,size in seen},{900})
        self.assertEqual(len({size for _,size in seen}),1)

    def test_phone_portrait_sizes_and_landscape_rejection(self):
        self.assertEqual(render.video_size(),(1080,1920))
        for width in (180,540,720,1080,2160):
            w,h=render.video_size(width)
            self.assertEqual(w*16,h*9)
            self.assertLess(w,h)
        data=copy.deepcopy(self.episode)
        data["aspect_ratio"]="16:9"
        with self.assertRaises(ValueError):
            render.validate(data)
        data=copy.deepcopy(self.episode)
        data["layout"]="cards"
        with self.assertRaises(ValueError):
            render.validate(data)

    def test_full_bleed_scene_has_no_title_or_footer_bands(self):
        from PIL import ImageChops
        data=render.validate(self.episode)
        for setting in ("classroom","schoolyard","street"):
            scene=dict(data["scenes"][0],index=100,setting=setting,start=0,end=5,
                       voice_start=.18,voice_end=4.5,envelope=[0]*120)
            first=Stage(ROOT/"assets",data,find_font()).frame(scene,2,24)
            changed=copy.deepcopy(data)
            changed["brand"]="不燒在畫面上"
            changed["footer"]="沒有底部白色文字區"
            second_scene=dict(scene,headline="這是審稿標題")
            second=Stage(ROOT/"assets",changed,find_font()).frame(second_scene,2,24)
            self.assertIsNone(ImageChops.difference(first,second).getbbox())
            for point in ((5,5),(1075,1915)):
                self.assertNotEqual(first.getpixel(point),(255,249,237))
            self.assertEqual(first.size,(1080,1920))

    def test_hands_and_mouth_animate_without_resizing_the_body(self):
        from PIL import ImageChops
        stage=Stage(ROOT/"assets",render.validate(self.episode),find_font())
        for name in ("doctor","alo","mei"):
            rest=stage.character_sprite(name,780,0,0)
            point=stage.character_sprite(name,780,0,0,gesture="point",phase=2)
            moving=stage.character_sprite(name,780,0,0,gesture="talk",phase=1)
            moved=stage.character_sprite(name,780,0,0,gesture="talk",phase=4)
            talking=stage.character_sprite(name,780,3,0)
            self.assertEqual(rest.size,point.size)
            self.assertIsNotNone(ImageChops.difference(rest,point).getbbox())
            self.assertIsNotNone(ImageChops.difference(moving,moved).getbbox())
            self.assertIsNotNone(ImageChops.difference(rest,talking).getbbox())
            self.assertIsNone(ImageChops.difference(rest.crop((0,620,rest.width,780)),
                                                  point.crop((0,620,point.width,780))).getbbox())

    def test_articulated_arms_keep_lengths_and_connected_sleeves(self):
        from arms import arm_pose
        stage=Stage(ROOT/"assets",render.validate(self.episode),find_font())
        for name in ("doctor","alo","mei"):
            rig=stage.rigs[name]
            for direction in (-1,1):
                for gesture in ("talk","point","present","question","wave"):
                    for phase in range(6):
                        pose=arm_pose(rig,stage.characters[name].size,780,gesture,phase,direction)
                        self.assertAlmostEqual(math.dist(pose["shoulder"],pose["elbow"]),pose["upper_length"],places=6)
                        self.assertAlmostEqual(math.dist(pose["elbow"],pose["wrist"]),pose["lower_length"],places=6)
                        bend=abs(pose["upper_angle"]-pose["fore_angle"])
                        self.assertTrue(20<=bend<=140)
                    if gesture not in ("point","question","present"):
                        continue
                    sprite=stage.character_sprite(name,780,0,0,gesture=gesture,phase=2,direction=direction)
                    pose=arm_pose(rig,stage.characters[name].size,780,gesture,2,direction)
                    pad=stage.character_parts(name,780)[2]
                    for start,end in ((pose["shoulder"],pose["elbow"]),(pose["elbow"],pose["wrist"]),(pose["wrist"],pose["hand"])):
                        for k in range(11):
                            fraction=k/10
                            x=round(pad+start[0]+(end[0]-start[0])*fraction)
                            y=round(start[1]+(end[1]-start[1])*fraction)
                            self.assertGreaterEqual(sprite.getpixel((x,y))[3],240,
                                                    f"Disconnected {name}/{gesture}/{direction} at {(x,y)}")

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
        diff=ImageChops.difference(with_model.crop((450,1040,630,1410)),
                                   no_model.crop((450,1040,630,1410)))
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
            episode["pacing"]={"speech_speed":1.0,"lead_in":.03,"trim_silence":False}
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
            self.assertIn(b"SAR 1:1 DAR 9:16",result.stderr)
            self.assertEqual(manifest["aspect_ratio"],"9:16")
            self.assertIn(b"Audio: aac",result.stderr)
            self.assertGreater((output/"episode.srt").stat().st_size,50)
            with wave.open(str(output/"mix.wav"),"rb") as mix:
                self.assertAlmostEqual(mix.getnframes()/mix.getframerate(),manifest["duration"],places=3)


if __name__=="__main__":
    unittest.main()
