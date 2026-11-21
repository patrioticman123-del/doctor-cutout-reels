#!/usr/bin/env python3
"""Render a fact-checked episode JSON to voiced vertical cut-paper MP4."""
import argparse
from datetime import date
import html
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw
import imageio_ffmpeg

from audio import assemble
from visuals import Stage, chunks, find_font, fit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VOICES = {
    "doctor": {"edge": "zh-TW-YunJheNeural", "sapi": "Microsoft Zhiwei"},
    "alo": {"edge": "zh-TW-HsiaoChenNeural", "sapi": "Microsoft Hanhan Desktop"},
    "mei": {"edge": "zh-TW-HsiaoYuNeural", "sapi": "Microsoft Yating"},
    "narrator": {"edge": "zh-TW-HsiaoChenNeural", "sapi": "Microsoft Hanhan Desktop"}}


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("Episode must be an object")
    for field in ("title", "topic"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"Missing {field}")
    kind = data.get("content_type", "medical")
    if kind not in ("medical", "template"):
        raise ValueError("content_type must be medical or template")
    data["content_type"] = kind
    for field, default, limit in [("brand","醫師剪紙劇場",14),
                                  ("footer","一般衛教資訊 · 個別狀況請諮詢醫師",28)]:
        data.setdefault(field, default)
        if not isinstance(data[field],str) or not 1 <= len(data[field]) <= limit:
            raise ValueError(f"{field} must have 1–{limit} characters")
    data.setdefault("names",{"doctor":"醫師","alo":"阿洛","mei":"美芳","narrator":"旁白"})
    for name in DEFAULT_VOICES:
        if not isinstance(data["names"].get(name),str) or not 1<=len(data["names"][name])<=8:
            raise ValueError(f"names.{name} must have 1–8 characters")
    data.setdefault("voices", DEFAULT_VOICES)
    for speaker in DEFAULT_VOICES:
        settings = data["voices"].setdefault(speaker, DEFAULT_VOICES[speaker])
        for provider in ("sapi", "edge"):
            if not isinstance(settings.get(provider), str) or not settings[provider]:
                raise ValueError(f"voices.{speaker}.{provider} is missing")
    sources = data.setdefault("sources", [])
    if not isinstance(sources,list):
        raise ValueError("sources must be an array")
    ids=set()
    for source in sources:
        for field in ("id","title","url","accessed","supports"):
            if not isinstance(source.get(field),str) or not source[field].strip():
                raise ValueError(f"Source missing {field}")
        if source["id"] in ids:
            raise ValueError("Duplicate source id")
        ids.add(source["id"])
        if not source["url"].startswith(("https://","http://")):
            raise ValueError("Source URL must be http(s)")
        date.fromisoformat(source["accessed"])
    scenes = data.get("scenes")
    if not isinstance(scenes,list) or not 2 <= len(scenes) <= 14:
        raise ValueError("Provide 2–14 scenes")
    claim_count=0
    for i,scene in enumerate(scenes):
        if not isinstance(scene,dict):
            raise ValueError(f"Scene {i+1} must be an object")
        for field,limit in (("text",140),("headline",26),("beat",40)):
            if not isinstance(scene.get(field),str) or not 1 <= len(scene[field].strip()) <= limit:
                raise ValueError(f"Scene {i+1}: {field} must have 1–{limit} characters")
        if scene.get("speaker") not in DEFAULT_VOICES:
            raise ValueError(f"Scene {i+1}: invalid speaker")
        if scene.get("shot") not in ("wide","doctor","alo","mei","punch"):
            raise ValueError(f"Scene {i+1}: invalid shot")
        if scene.get("setting") not in ("classroom","schoolyard","street"):
            raise ValueError(f"Scene {i+1}: invalid setting")
        cast=scene.get("cast")
        if not isinstance(cast,list) or not 2<=len(cast)<=3 or len(set(cast))!=len(cast) or any(c not in ("doctor","alo","mei") for c in cast):
            raise ValueError(f"Scene {i+1}: cast must list 2–3 distinct supported characters")
        if scene["speaker"]!="narrator" and scene["speaker"] not in cast:
            raise ValueError(f"Scene {i+1}: speaker must be visible in cast")
        for field in ("action","reaction"):
            if not isinstance(scene.get(field),str) or not scene[field].strip():
                raise ValueError(f"Scene {i+1}: {field} is required for storyboard review")
        scene.setdefault("motion","nod")
        if scene["motion"] not in ("nod","shake","still"):
            raise ValueError(f"Scene {i+1}: motion must be nod, shake or still")
        scene.setdefault("hold",.4)
        if isinstance(scene["hold"],bool) or not isinstance(scene["hold"],(int,float)) or not .1 <= scene["hold"] <= 2:
            raise ValueError(f"Scene {i+1}: hold must be 0.1–2 seconds")
        claims=scene.setdefault("claims",[])
        if not isinstance(claims,list) or any(not isinstance(c,str) or c not in ids for c in claims):
            raise ValueError(f"Scene {i+1}: claims reference unknown source IDs")
        claim_count+=len(claims)
    if kind == "medical" and (not sources or not claim_count):
        raise ValueError("Medical episodes require sources and scene-level claims references")
    if sum(s["speaker"]!="narrator" for s in scenes)/len(scenes)<.75:
        raise ValueError("At least 75% of scenes must be character dialogue")
    return data


def revision(episode):
    """Invalidate approval after script, renderer, rig, or image changes."""
    digest=hashlib.sha256(json.dumps(episode,ensure_ascii=False,sort_keys=True).encode())
    for folder,extensions in [(ROOT/"assets",(".json",".png")),(ROOT/"scripts",(".py",".ps1"))]:
        for path in sorted(folder.iterdir()):
            if path.suffix in extensions:
                digest.update(path.name.encode())
                content=path.read_bytes()
                digest.update(content if path.suffix==".png" else content.replace(b"\r\n",b"\n"))
    return digest.hexdigest()[:16]


def draft(episode,out,font_path):
    """No TTS/network/audio/video calls: review script and composed still frames."""
    out.mkdir(parents=True,exist_ok=True)
    stage=Stage(ROOT/"assets",episode,font_path)
    frames=out/"frames"
    frames.mkdir(exist_ok=True)
    rev=revision(episode)
    thumbnails=[]
    timeline=[]
    cursor=0
    rows=[f"# {episode['title']}\n",f"分鏡版本：`{rev}`\n",
          "狀態：待使用者審閱。尚未生成配音、配樂或影片。\n",
          "秒數為讀劇估計；核准後依實際配音調整為 30–60 秒。\n"]
    cards=[]
    for i,scene in enumerate(episode["scenes"]):
        length=max(2.0,len(scene["text"])/4.3)
        end=cursor+.18+length+scene["hold"]
        item=dict(scene,index=i,start=cursor,end=end,voice_start=cursor+.18,
                  voice_end=cursor+.18+length,envelope=[0.0]*math.ceil(length*24))
        frame=stage.frame(item,(cursor+end)/2,24)
        image_name=f"frames/{i+1:02}.jpg"
        frame.save(out/image_name,quality=91)
        thumbnails.append(frame.resize((270,480),Image.Resampling.LANCZOS))
        name=episode["names"][scene["speaker"]]
        setting={"classroom":"教室","schoolyard":"小學校園","street":"街道"}[scene["setting"]]
        shot_label={"wide":"固定尺度・全員同框","doctor":"固定尺度・醫師發言",
                    "alo":"固定尺度・阿洛發言","mei":"固定尺度・美芳發言",
                    "punch":"固定尺度・笑點留白"}[scene["shot"]]
        beat_label={"hook":"開場衝突","turn":"轉折","escalate":"誤解升級","explain":"釐清",
                    "character":"角色接話","dialogue":"追問","workflow":"製作流程",
                    "punch":"笑點","cta":"行動"}.get(scene["beat"],scene["beat"])
        cast="、".join(episode["names"][c] for c in scene["cast"])
        rows += [f"## {i+1:02} · {setting} · {beat_label} · 約 {end-cursor:.1f} 秒\n",
                 f"角色：{cast}｜鏡頭：{shot_label}\n",
                 f"**{name}：** {scene['text']}\n",f"動作：{scene['action']}\n",
                 f"接話／反應：{scene['reaction']}\n",f"字卡：{scene['headline']}\n",
                 f"來源：{', '.join(scene['claims']) or '純劇情／範本，不含臨床說法'}\n"]
        esc=html.escape
        cards.append(f'<article><img src="{image_name}" alt="分鏡 {i+1}"><div><small>{i+1:02} · {setting} · {end-cursor:.1f}s（估）</small><h2>{esc(scene["headline"])}</h2><p><b>{esc(name)}：</b>{esc(scene["text"])}</p><p>動作：{esc(scene["action"])}</p><p>反應：{esc(scene["reaction"])}</p><p>鏡頭：{esc(shot_label)} · 來源：{esc(", ".join(scene["claims"]) or "無臨床說法")}</p></div></article>')
        timeline.append({k:v for k,v in item.items() if k!="envelope"})
        cursor=end
    sheet=Image.new("RGB",(810,480*math.ceil(len(thumbnails)/3)),"#FFF9ED")
    for i,image in enumerate(thumbnails):
        sheet.paste(image,((i%3)*270,(i//3)*480))
    sheet.save(out/"storyboard.jpg",quality=93)
    rows += ["## 醫療來源\n"]
    for source in episode["sources"]:
        rows.append(f"- {source['id']} — [{source['title']}]({source['url']})；查閱 {source['accessed']}；支持：{source['supports']}\n")
    rows += ["## 修改與確認\n","請以幕號回覆修改；修改後會重新交付腳本與分鏡。確認此版本後，才進入配音配樂及影片階段。\n"]
    (out/"script.md").write_text("\n".join(rows),encoding="utf-8")
    manifest={"status":"awaiting_user_review","revision":rev,"estimated_duration":cursor,
              "target_duration":[30,60],"sources":episode["sources"],"timeline":timeline}
    (out/"draft.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"episode.json").write_text(json.dumps(episode,ensure_ascii=False,indent=2),encoding="utf-8")
    page=f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(episode['title'])}・分鏡審稿</title><style>body{{background:#fff9ed;color:#202332;font:17px system-ui;max-width:1100px;margin:40px auto;padding:0 20px}}article{{display:grid;grid-template-columns:230px 1fr;gap:28px;border-top:3px solid #202332;padding:25px 0}}img{{width:100%}}h1{{font-size:30px}}small{{color:#666}}p{{line-height:1.7}}.status{{padding:18px;background:#f8c854}}a{{color:#315d57}}@media(max-width:600px){{article{{grid-template-columns:1fr}}img{{max-width:270px}}}}</style><h1>{html.escape(episode['title'])}</h1><p class="status">待審稿 · 版本 {rev} · 約 {cursor:.1f} 秒（估）<br>尚未生成配音、配樂或影片。請先修改或確認腳本與分鏡。</p><p><a href="script.md">完整腳本</a> · <a href="storyboard.jpg">分鏡總覽</a> · <a href="episode.json">劇本資料</a></p>{''.join(cards)}</html>'''
    (out/"storyboard.html").write_text(page,encoding="utf-8")
    print(f"DRAFT: {out/'storyboard.html'} | revision {rev} | estimated {cursor:.1f}s",flush=True)
    return manifest


def timestamp(t):
    ms=round(t*1000)
    seconds,ms=divmod(ms,1000)
    minutes,seconds=divmod(seconds,60)
    hours,minutes=divmod(minutes,60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def subtitles(timeline):
    rows=[]
    for scene in timeline:
        parts=chunks(scene["text"])
        total=sum(map(len,parts))
        start=scene["voice_start"]
        for caption in parts:
            end=start+(scene["voice_end"]-scene["voice_start"])*len(caption)/total
            rows.append(f"{len(rows)+1}\n{timestamp(start)} --> {timestamp(end)}\n{caption}\n")
            start=end
    return "\n".join(rows)


def render(episode, source_dir, out, backend, width, fps, font_path):
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    out.mkdir(parents=True,exist_ok=True)
    stage=Stage(ROOT/"assets",episode,font_path)
    timeline,duration=assemble(episode,backend,source_dir,out,ffmpeg,fps)
    # The requested length is measured AFTER speech generation; no audio is truncated.
    if not 30 <= duration <= 60:
        raise ValueError(f"Measured duration is {duration:.2f}s; required 30–60s. "
                         "Rewrite dialogue/holds, then rerun. Cached speech is retained.")
    height=width*16//9
    temp=out/"episode.rendering.mp4"
    log_path=out/"ffmpeg.log"
    command=[ffmpeg,"-y","-v","warning","-f","rawvideo","-pix_fmt","rgb24",
             "-s",f"{width}x{height}","-r",str(fps),"-i","pipe:0",
             "-i",str(out/"mix.wav"),"-map","0:v:0","-map","1:a:0",
             "-c:v","libx264","-preset","fast","-crf","19","-pix_fmt","yuv420p",
             "-c:a","aac","-b:a","160k","-ar","48000",
             "-movflags","+faststart","-t",f"{duration:.6f}",str(temp)]
    total=round(duration*fps)
    thumbnails=[]
    index=0
    process=None
    try:
        with log_path.open("wb") as log:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
            for n in range(total):
                t=n/fps
                while index < len(timeline)-1 and t >= timeline[index]["end"]:
                    index+=1
                frame=stage.frame(timeline[index],t,fps)
                if n == round(((timeline[index]["start"]+timeline[index]["end"])/2)*fps):
                    thumbnails.append(frame.resize((270,480),Image.Resampling.LANCZOS))
                if width!=1080:
                    frame=frame.resize((width,height),Image.Resampling.LANCZOS)
                process.stdin.write(frame.tobytes())
                if n % max(1,total//10)==0:
                    print(f"Render {n/total:.0%}",flush=True)
            process.stdin.close()
            if process.wait():
                raise RuntimeError(log_path.read_text(encoding="utf-8",errors="replace")[-3000:])
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        temp.unlink(missing_ok=True)
        raise
    temp.replace(out/"episode.mp4")
    sheet=Image.new("RGB",(270*3,480*math.ceil(len(thumbnails)/3)),"#FFF9ED")
    for i,im in enumerate(thumbnails):
        sheet.paste(im,((i%3)*270,(i//3)*480))
    sheet.save(out/"render-storyboard.jpg",quality=93)
    (out/"episode.srt").write_text(subtitles(timeline),encoding="utf-8-sig")
    manifest={"title":episode["title"],"topic":episode["topic"],"content_type":episode["content_type"],
              "duration":duration,"width":width,"height":height,"fps":fps,"speech_backend":backend,
              "voices":episode["voices"],"sources":episode["sources"],
              "timing":"measured PCM speech; proportional subtitle chunks; amplitude mouth animation",
              "timeline":[{k:v for k,v in s.items() if k!="envelope"} for s in timeline],
              "outputs":["episode.mp4","episode.srt","preview.html","render-storyboard.jpg","voice.wav","music.wav","mix.wav"]}
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"episode.json").write_text(json.dumps(episode,ensure_ascii=False,indent=2),encoding="utf-8")
    title=html.escape(episode["title"])
    (out/"preview.html").write_text(f'''<!doctype html>
<html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>body{{background:#202332;color:#fff9ed;font:16px system-ui;margin:24px auto;max-width:700px;padding:0 20px}}video{{height:min(75vh,900px);max-width:100%;display:block;margin:auto;border-radius:12px}}a{{color:#f8c854}}h1{{font-size:24px}}.links{{display:flex;gap:20px;flex-wrap:wrap;margin:24px 0}}</style>
<h1>{title}</h1><p>{duration:.1f} 秒 · {width}×{height} · 合成角色配音 / 原創程序配樂</p>
<video controls playsinline preload="metadata" src="episode.mp4"></video>
<div class="links"><a href="episode.mp4" download>下載 MP4</a><a href="episode.srt" download>下載字幕</a><a href="render-storyboard.jpg">查看成片抽幀</a><a href="manifest.json">來源與時間軸</a></div>
<p>需與同資料夾的影片檔一起使用。音樂、人聲及字幕已輸出到影片。</p></html>''',encoding="utf-8")
    print(f"DONE: {out/'episode.mp4'} ({duration:.2f}s)",flush=True)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode",type=Path)
    parser.add_argument("--out",type=Path,default=Path("build/episode"))
    parser.add_argument("--voice",choices=("sapi","edge","files"),default="sapi" if sys.platform=="win32" else "edge")
    parser.add_argument("--width",type=int,default=1080)
    parser.add_argument("--fps",type=int,default=24)
    parser.add_argument("--font")
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--render",action="store_true",help="Render only after user approval of this revision")
    parser.add_argument("--approved-hash",help="Revision explicitly approved by user; must match draft.json and current assets")
    args=parser.parse_args()
    try:
        if args.width < 180 or args.width > 2160 or args.width % 18:
            raise ValueError("Width must be a multiple of 18 between 180 and 2160")
        if not 1 <= args.fps <= 60:
            raise ValueError("fps must be 1–60")
        data=validate(json.loads(args.episode.read_text(encoding="utf-8-sig")))
        face=find_font(args.font)
        for scene in data["scenes"]:
            fit(scene["headline"],face,81,950,2)
            for part in chunks(scene["text"]):
                fit(part,face,66,944,2)
        if args.check:
            print("Episode structure, source references and text layout valid. Medical accuracy requires source review.")
            return 0
        if not args.render:
            draft(data,args.out.resolve(),face)
            return 0
        draft_path=args.out.resolve()/"draft.json"
        if not draft_path.exists():
            raise ValueError("Create and review a draft before rendering (omit --render).")
        approved=json.loads(draft_path.read_text(encoding="utf-8"))
        if not args.approved_hash or args.approved_hash!=approved.get("revision") or args.approved_hash!=revision(data):
            raise ValueError("Missing/stale approval hash. Present the current draft to the user first.")
        render(data,args.episode.resolve().parent,args.out.resolve(),args.voice,args.width,args.fps,face)
        return 0
    except (ValueError,RuntimeError,OSError,KeyError,TypeError) as error:
        print(f"ERROR: {error}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
