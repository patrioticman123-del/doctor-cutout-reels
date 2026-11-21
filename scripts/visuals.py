"""Original cut-paper school/neighborhood sets and an original recurring cast."""
from functools import lru_cache
import math
import os
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont

INK = "#202332"
PAPER = "#FFF9ED"
YELLOW = "#F8C854"
CORAL = "#EF745C"
W, H = 1080, 1920
TEACHING_LABELS = {"dialogue":"角色對話", "blackboard":"黑板講解",
                   "bone_model":"骨頭模型示範", "quiz":"學生猜題", "comparison":"並列比較"}
GESTURE_LABELS = {"auto":"依對話選擇", "rest":"放鬆聆聽", "talk":"說話擺手",
                  "point":"指向黑板", "present":"攤手介紹", "question":"舉手提問", "wave":"揮手"}


def resolved_gesture(scene):
    value=scene.get("gesture","auto")
    if value!="auto":
        return value
    mode=scene.get("teaching",{}).get("mode","dialogue")
    if scene["speaker"]=="doctor" and mode in ("blackboard","quiz","comparison"):
        return "point"
    if mode=="bone_model":
        return "present"
    return "question" if scene["speaker"]=="alo" else "talk"


def gesture_angles(gesture,phase,direction=1):
    wave=math.sin(phase*math.tau/6)
    if gesture=="talk":
        left,right=0,14+12*wave
    elif gesture=="point":
        left,right=0,60+5*wave
    elif gesture=="present":
        left,right=0,45+8*wave
    elif gesture=="question":
        left,right=0,85+8*wave
    elif gesture=="wave":
        left,right=0,100+12*wave
    else:
        left,right=0,0
    if direction<0:
        left,right=-right,-left
    return round(left/5)*5,round(right/5)*5


def find_font(explicit=None):
    paths = [explicit] if explicit else []
    paths += [os.environ.get("CJK_FONT"), "C:/Windows/Fonts/msjhbd.ttc",
              "/System/Library/Fonts/PingFang.ttc",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]
    for p in paths:
        if p and Path(p).is_file():
            return str(p)
    raise ValueError("No CJK font found. Install Noto Sans CJK or pass --font PATH.")


@lru_cache(maxsize=64)
def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(text, face, width):
    lines, line = [], ""
    for char in text:
        if char == "\n":
            lines.append(line)
            line = ""
        elif line and face.getlength(line + char) > width:
            lines.append(line)
            line = char
        else:
            line += char
    if line:
        lines.append(line)
    return lines


def fit(text, path, max_size, width, max_lines=2):
    for size in range(max_size, 35, -2):
        face = font(path, size)
        lines = wrap(text, face, width)
        if len(lines) <= max_lines:
            return face, lines
    raise ValueError(f"Text too long to fit safely: {text}")


def chunks(text, limit=27):
    # Prefer a punctuation boundary; retain every character and clinical qualifier.
    pieces = re.findall(r"[^，。！？；、,.!?;]+[，。！？；、,.!?;]?", text)
    result, buf = [], ""
    for piece in pieces:
        while len(piece) > limit:
            if buf:
                result.append(buf)
                buf = ""
            result.append(piece[:limit])
            piece = piece[limit:]
        if buf and len(buf)+len(piece) > limit:
            result.append(buf)
            buf = ""
        buf += piece
    if buf:
        result.append(buf)
    return result or [text]


def subtitle_at(scene, t):
    captions = chunks(scene["text"])
    total = sum(len(c) for c in captions)
    fraction = min(.999999, max(0, (t-scene["voice_start"]) /
                               (scene["voice_end"]-scene["voice_start"])))
    current = fraction * total
    for caption in captions:
        if current < len(caption):
            return caption
        current -= len(caption)
    return captions[-1]


class Stage:
    def __init__(self, assets, episode, font_path):
        import json
        self.episode = episode
        self.font_path = font_path
        self.rigs = json.loads((assets / "cast.json").read_text(encoding="utf-8"))
        self.characters = {name:Image.open(assets / rig["image"]).convert("RGBA")
                           for name,rig in self.rigs.items()}
        self.backgrounds = {}
        self.sprites = {}
        self.arm_layers = {}
        self.caption_cache = {}

    def text(self, draw, xy, value, size, fill=INK, anchor=None):
        draw.text(xy, value, font=font(self.font_path, size), fill=fill, anchor=anchor)

    def background(self, scene):
        from scenery import draw_scene
        key=scene["index"]
        if key not in self.backgrounds:
            self.backgrounds[key]=draw_scene(scene,self.text)
        return self.backgrounds[key].copy()

    def character_parts(self,name,height):
        """Hinge the existing cut-paper sleeves/hands; retain the original body scale."""
        key=(name,height)
        if key in self.arm_layers:
            return self.arm_layers[key]
        from PIL import ImageChops, ImageOps
        source=self.characters[name]
        rig=self.rigs[name]
        iw,ih=source.size
        sx,sy=rig["shoulder"]
        top,end=rig["arm_start"],rig["arm_end"]
        polygon=[(sx+.015,top),(.335,top+.08),(.327,.58),(.307,.655),
                 (.305,end),(.08,end),(.08,top)]
        masks=[]
        for side in (0,1):
            mask=Image.new("L",source.size)
            ImageDraw.Draw(mask).polygon([(round((1-x if side else x)*iw),round(y*ih))
                                         for x,y in polygon],fill=255)
            masks.append(mask)
        alpha=source.getchannel("A")
        body=source.copy()
        body.putalpha(ImageChops.multiply(alpha,ImageOps.invert(ImageChops.lighter(*masks))))
        pieces=[body]
        for mask in masks:
            limb=source.copy()
            limb.putalpha(ImageChops.multiply(alpha,mask))
            pieces.append(limb)
        pad=180
        size=(round((iw+2*pad)*height/ih),height)
        padded=[]
        for piece in pieces:
            layer=Image.new("RGBA",(iw+2*pad,ih))
            layer.alpha_composite(piece,(pad,0))
            padded.append(layer.resize(size,Image.Resampling.LANCZOS))
        scale=height/ih
        pivots=[((pad+sx*iw)*scale,sy*ih*scale),
                ((pad+(1-sx)*iw)*scale,sy*ih*scale)]
        value=(padded,pivots,round(pad*scale))
        self.arm_layers[key]=value
        return value

    def hand_anchor(self,name,height,gesture,phase,direction):
        rig=self.rigs[name]
        iw,ih=self.characters[name].size
        sx,sy=rig["shoulder"]
        hx,hy=rig["hand"]
        side=1 if direction>0 else 0
        px=(1-sx if side else sx)*iw
        py=sy*ih
        x=(1-hx if side else hx)*iw
        y=hy*ih
        angle=math.radians(gesture_angles(gesture,phase,direction)[side])
        dx,dy=x-px,y-py
        return ((px+dx*math.cos(angle)+dy*math.sin(angle))*height/ih,
                (py-dx*math.sin(angle)+dy*math.cos(angle))*height/ih)

    def character_sprite(self, name, height, mouth, blink, gesture="rest", phase=0, direction=1):
        if gesture=="rest":
            phase=0
        key = (name, height, mouth, blink, gesture, phase, direction)
        if key in self.sprites:
            return self.sprites[key]
        pieces,pivots,pad=self.character_parts(name,height)
        image=pieces[0].copy()
        for arm,pivot,angle in zip(pieces[1:],pivots,gesture_angles(gesture,phase,direction)):
            image.alpha_composite(arm.rotate(angle,resample=Image.Resampling.BICUBIC,center=pivot)
                                  if angle else arm)
        rig = self.rigs[name]
        draw = ImageDraw.Draw(image)
        iw,ih=self.characters[name].size
        scale=height/ih
        mx,my=pad+rig["mouth"][0]*iw*scale,rig["mouth"][1]*height
        mw=rig["mouth_width"]*iw*scale
        if mouth:
            draw.rounded_rectangle((mx-mw*.65,my-4,mx+mw*.65,my+4),radius=3,fill=rig["skin"])
            width=mw*(.8 if mouth==3 else (1.2 if mouth==2 else 1))
            mh=(10,18,27)[mouth-1]
            draw.ellipse((mx-width/2,my-mh/2,mx+width/2,my+mh/2), fill="#271F26")
            if mouth==2:
                draw.rectangle((mx-width*.28,my-mh*.32,mx+width*.28,my-mh*.05),fill="#FFF8ED")
            if mouth==3:
                draw.ellipse((mx-width*.25,my+mh*.12,mx+width*.25,my+mh*.4),fill="#D37A77")
        if blink:
            for ex,ey in rig["eyes"]:
                x,y = pad+ex*iw*scale,ey*height
                draw.ellipse((x-62*scale,y-77*scale,x+62*scale,y+77*scale),fill=rig["skin"])
                draw.line((x-62*scale,y,x+62*scale,y),fill=INK,width=4)
        if len(self.sprites)>=96:
            self.sprites.pop(next(iter(self.sprites)))
        self.sprites[key] = image
        return image

    def teaching_panel(self, scene):
        lesson=scene.get("teaching",{"mode":"dialogue"})
        mode=lesson["mode"]
        if mode=="dialogue":
            return None
        key=("teaching",scene["index"])
        if key in self.backgrounds:
            return self.backgrounds[key]
        panel=Image.new("RGBA",(W,H))
        d=ImageDraw.Draw(panel)
        chalk="#F7F0CF"
        # Center teaching area leaves both actors at the exact same locked scale.
        d.rectangle((200,110,880,720),fill="#855D48",outline=INK,width=8)
        d.rectangle((218,128,862,702),fill="#315D57",outline=INK,width=4)
        face,lines=fit(lesson["title"],self.font_path,52,570,2)
        for j,line in enumerate(lines):
            d.text((250,155+j*60),line,font=face,fill=chalk)
        d.line((250,290,830,290),fill=chalk,width=3)
        points=lesson["points"]
        if mode=="comparison":
            for j,point in enumerate(points):
                x=240+j*310
                d.rounded_rectangle((x,335,x+290,665),radius=8,fill="#F7F0CF",outline=INK,width=4)
                face,lines=fit(point,self.font_path,46,250,3)
                for k,line in enumerate(lines):
                    d.text((x+20,375+k*62),line,font=face,fill=INK)
        else:
            for j,point in enumerate(points):
                y=330+j*115
                prefix=chr(65+j)+" " if mode=="quiz" else "• "
                face,lines=fit(prefix+point,self.font_path,44,570,2)
                for k,line in enumerate(lines):
                    d.text((250,y+k*50),line,font=face,fill=chalk)
                if mode=="blackboard" and j<len(points)-1:
                    d.line((800,y+75,800,y+96),fill=YELLOW,width=4)
                    d.polygon([(792,y+88),(800,y+99),(808,y+88)],fill=YELLOW)
        # Chalk tray and freestanding supports also work on the street/campus.
        d.rectangle((190,720,890,746),fill="#B58C61",outline=INK,width=4)
        d.rectangle((755,710,805,719),fill=chalk)
        d.line((260,746,220,1500),fill=INK,width=9)
        d.line((820,746,860,1500),fill=INK,width=9)
        self.backgrounds[key]=panel
        return panel

    def teaching_props(self, scene):
        lesson=scene.get("teaching",{"mode":"dialogue"})
        if lesson["mode"]=="dialogue":
            return None
        key=("props",scene["index"])
        if key in self.backgrounds:
            return self.backgrounds[key]
        layer=Image.new("RGBA",(W,H))
        d=ImageDraw.Draw(layer)
        if lesson["mode"]=="bone_model":
            # Generic teaching prop, deliberately not a clinical anatomy diagram.
            d.rectangle((350,1410,730,1460),fill="#D19B61",outline=INK,width=7)
            d.line((380,1460,370,1730),fill=INK,width=12)
            d.line((700,1460,710,1730),fill=INK,width=12)
            d.ellipse((460,1360,620,1405),fill="#91A7A4",outline=INK,width=6)
            d.line((540,1230,540,1380),fill=INK,width=8)
            # An outline mask makes a single clean paper-cut bone silhouette.
            shape=Image.new("L",(W,H))
            sd=ImageDraw.Draw(shape)
            sd.rounded_rectangle((518,1084,562,1295),radius=18,fill=255)
            for box in [(479,1050,548,1120),(535,1051,604,1121),
                        (479,1260,548,1330),(535,1260,604,1330)]:
                sd.ellipse(box,fill=255)
            from PIL import ImageFilter
            outline=shape.filter(ImageFilter.MaxFilter(13))
            layer.paste(INK,(0,0,W,H),outline)
            layer.paste("#F5EAD1",(0,0,W,H),shape)
            d=ImageDraw.Draw(layer)
            d.rounded_rectangle((380,1472,700,1525),radius=6,fill=PAPER,outline=INK,width=3)
            self.text(d,(540,1476),"骨頭教具・示意",32,INK,"ma")
        self.backgrounds[key]=layer
        return layer

    def frame(self, scene, t, fps):
        im=self.background(scene)
        lesson=scene.get("teaching",{"mode":"dialogue"})
        panel=self.teaching_panel(scene)
        if panel is not None:
            im.paste(panel,(0,0),panel)
        local=t-scene["start"]
        speaking=scene["voice_start"] <= t < scene["voice_end"]
        pos=int(max(0,t-scene["voice_start"])*fps)
        level=scene["envelope"][min(pos,len(scene["envelope"])-1)] if speaking else 0
        mouth=0 if level < .08 else min(3,1+int(level*2.8))
        draft_pose=scene.get("draft_pose",False)
        if draft_pose:
            mouth=2
        blink=0 if draft_pose else int(int(t*12)%53 in (0,1))
        step=round(local*10)/10  # Intentionally stepped cut-paper movement.
        bounce=round(math.sin(step*13)*5) if speaking and level>.08 else 0
        shot=scene["shot"]
        cast=scene["cast"]
        focus=scene["speaker"] if shot=="punch" else shot
        # One locked scale for EVERY actor in EVERY board. Focus never shrinks
        # listeners or enlarges a speaker. Shared baseline keeps feet aligned.
        positions=(-100,240,580) if len(cast)==3 else (-85,565)
        layout={name:(positions[i],760,900) for i,name in enumerate(cast)}
        # Compose in a masked stage to protect the subtitle safe area.
        stage=Image.new("RGBA",(W,H))
        pointer=None
        selected_gesture=resolved_gesture(scene)
        draw_order=list(cast)
        for name in draw_order:
            x,y,height=layout[name]
            active=scene["speaker"]==name
            direction=1 if x<300 else -1
            gesture=selected_gesture if active and (draft_pose or speaking or selected_gesture=="point") else "rest"
            phase=2 if draft_pose else int(local*4)%6
            sprite=self.character_sprite(name,height,mouth if scene["speaker"]==name else 0,
                                         blink if name!="mei" else 0,gesture=gesture,phase=phase,direction=direction)
            motion=scene.get("motion","nod")
            ox=bounce if active and motion=="shake" else 0
            oy=bounce if active and motion=="nod" else 0
            pad=self.character_parts(name,height)[2]
            stage.alpha_composite(sprite,(x-pad+ox,y+oy))
            if active and gesture=="point" and lesson["mode"] not in ("dialogue","bone_model"):
                hx,hy=self.hand_anchor(name,height,gesture,phase,direction)
                pointer=(x+ox+hx,y+oy+hy)
        im.paste(stage,(0,0),stage)
        props=self.teaching_props(scene)
        if props is not None:
            im.paste(props,(0,0),props)
        d=ImageDraw.Draw(im)
        if pointer is not None:
            d.line((*pointer,540,640),fill=INK,width=10)
            d.line((*pointer,540,640),fill="#B58C61",width=5)
            d.ellipse((531,631,549,649),fill=YELLOW,outline=INK,width=3)
        if not self.episode.get("show_subtitles",True):
            return im
        caption=subtitle_at(scene,t)
        cache_key=(scene["index"],caption)
        if cache_key not in self.caption_cache:
            self.caption_cache[cache_key]=fit(caption,self.font_path,58,900,2)
        face,lines=self.caption_cache[cache_key]
        top=1750-(len(lines)-1)*72
        overlay=Image.new("RGBA",(W,H))
        ImageDraw.Draw(overlay).rounded_rectangle((65,top-10,1015,top+len(lines)*72+8),radius=12,fill=(15,20,28,160))
        im=Image.alpha_composite(im.convert("RGBA"),overlay).convert("RGB")
        d=ImageDraw.Draw(im)
        for j,line in enumerate(lines):
            d.text((540,top+j*72),line,font=face,fill="#FFFFFF",anchor="ma",stroke_width=2,stroke_fill="#10141C")
        return im
