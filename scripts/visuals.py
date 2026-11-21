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
        self.caption_cache = {}

    def text(self, draw, xy, value, size, fill=INK, anchor=None):
        draw.text(xy, value, font=font(self.font_path, size), fill=fill, anchor=anchor)

    def background(self, scene):
        key = scene["index"]
        if key in self.backgrounds:
            return self.backgrounds[key].copy()
        setting = scene["setting"]
        im = Image.new("RGB", (W, H), PAPER)
        d = ImageDraw.Draw(im)
        if setting == "classroom":
            d.rectangle((0,455,W,1470),fill="#E7C995")
            d.rectangle((45,540,730,980),fill="#855D48",outline=INK,width=9)
            d.rectangle((65,560,710,950),fill="#315D57",outline=INK,width=5)
            self.text(d,(100,595),"今天的健康課",53,"#F7F0CF")
            d.line((105,690,560,690),fill="#D5DEBE",width=5)
            d.rectangle((790,540,1040,980),fill="#FCF3DB",outline=INK,width=8)
            d.rectangle((810,560,1020,960),fill="#9ACACC")
            d.line((915,560,915,960),fill=INK,width=6)
            d.line((810,760,1020,760),fill=INK,width=6)
            d.rectangle((0,1235,W,1470),fill="#C79C75")
            for x in (100,480,860):
                d.line((x,1235,x-150,1470),fill="#A77B5B",width=4)
            for x in (75,520,880):
                d.polygon([(x,1130),(x+160,1130),(x+190,1185),(x-25,1185)],fill="#D49353",outline=INK,width=6)
                d.line((x,1185,x-10,1340),fill=INK,width=9)
                d.line((x+160,1185,x+170,1340),fill=INK,width=9)
        elif setting == "schoolyard":
            d.rectangle((0,455,W,1470),fill="#A9D2DA")
            d.ellipse((110,485,350,580),fill=PAPER)
            d.rectangle((60,650,1030,1250),fill="#E4BD87",outline=INK,width=9)
            d.polygon([(20,650),(545,500),(1070,650)],fill="#577F79",outline=INK,width=9)
            self.text(d,(545,665),"青禾小學",57,INK,"ma")
            for x in (115,305,705,890):
                for y in (790,1000):
                    d.rectangle((x,y,x+100,y+130),fill="#A6CDCE",outline=INK,width=7)
                    d.line((x+50,y,x+50,y+130),fill=INK,width=4)
            d.rectangle((470,1010,625,1250),fill="#755747",outline=INK,width=8)
            d.rectangle((0,1240,W,1470),fill="#8EB283")
            d.polygon([(460,1240),(630,1240),(890,1470),(200,1470)],fill="#D6CEB9")
            for x in (20,980):
                d.rectangle((x+30,1070,x+50,1310),fill="#80614D")
                d.ellipse((x-60,890,x+140,1130),fill="#57846A",outline=INK,width=7)
        else:  # Original neighborhood street; no copied town landmarks.
            d.rectangle((0,455,W,1470),fill="#AFCEDA")
            d.ellipse((80,500,320,590),fill=PAPER)
            for x,color,roof in [(-50,"#D6B5B9","#665D7D"),(380,"#E5CA94","#6B8D7E"),(810,"#B3C5AC","#9B6A60")]:
                d.rectangle((x,800,x+350,1240),fill=color,outline=INK,width=8)
                d.polygon([(x-25,800),(x+175,650),(x+375,800)],fill=roof,outline=INK,width=8)
                d.rectangle((x+40,865,x+140,1000),fill="#C6DFD8",outline=INK,width=6)
                d.rectangle((x+210,1040,x+300,1240),fill="#735E56",outline=INK,width=6)
            d.rectangle((0,1240,W,1320),fill="#D3CAB9",outline=INK,width=6)
            d.rectangle((0,1320,W,1470),fill="#686D78")
            for x in range(0,W,230):
                d.rectangle((x,1400,x+125,1415),fill="#F5E7AA")
        # Header and title remain in social-safe margins.
        d.rounded_rectangle((62,170,650,242), radius=9, fill=INK)
        self.text(d, (88,181), self.episode["brand"], 39, PAPER)
        self.text(d, (1015,185), f"{scene['index']+1:02}", 38, INK, "ra")
        face, lines = fit(scene["headline"], self.font_path, 81, 950, 2)
        for j,line in enumerate(lines):
            d.text((62,270+j*91),line,font=face,fill=INK)
        d.rectangle((0,1470,W,H),fill=PAPER)
        # Footer has generous margin above platform navigation.
        self.text(d,(65,1790),self.episode["footer"],31,"#5D6270")
        d.line((65,1765,1015,1765),fill=INK,width=3)
        self.backgrounds[key] = im
        return im.copy()

    def character_sprite(self, name, height, mouth, blink):
        key = (name, height, mouth, blink)
        if key in self.sprites:
            return self.sprites[key]
        image = self.characters[name].copy()
        rig = self.rigs[name]
        draw = ImageDraw.Draw(image)
        iw, ih = image.size
        mx,my = rig["mouth"][0]*iw,rig["mouth"][1]*ih
        mw = rig["mouth_width"]*iw
        if mouth:
            mh = (16+mouth*12)
            draw.ellipse((mx-mw/2,my-mh/2,mx+mw/2,my+mh/2), fill="#271F26")
            if mouth == 3:
                draw.ellipse((mx-mw*.25,my+mh*.12,mx+mw*.25,my+mh*.4),fill="#D37A77")
        if blink:
            for ex,ey in rig["eyes"]:
                x,y = ex*iw,ey*ih
                draw.ellipse((x-62,y-77,x+62,y+77),fill=rig["skin"])
                draw.line((x-62,y,x+62,y),fill=INK,width=8)
        image = image.resize((round(height*iw/ih),height),Image.Resampling.LANCZOS)
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
        d.rectangle((320,500,760,1040),fill="#855D48",outline=INK,width=8)
        d.rectangle((335,515,745,1025),fill="#315D57",outline=INK,width=4)
        face,lines=fit(lesson["title"],self.font_path,40,365,2)
        for j,line in enumerate(lines):
            d.text((355,535+j*49),line,font=face,fill=chalk)
        d.line((355,645,725,645),fill=chalk,width=3)
        points=lesson["points"]
        if mode=="comparison":
            for j,point in enumerate(points):
                x=348+j*197
                d.rounded_rectangle((x,690,x+184,985),radius=8,fill="#F7F0CF",outline=INK,width=4)
                face,lines=fit(point,self.font_path,36,155,3)
                for k,line in enumerate(lines):
                    d.text((x+13,725+k*52),line,font=face,fill=INK)
        else:
            for j,point in enumerate(points):
                y=685+j*100
                prefix=chr(65+j)+" " if mode=="quiz" else "• "
                face,lines=fit(prefix+point,self.font_path,36,365,2)
                for k,line in enumerate(lines):
                    d.text((355,y+k*44),line,font=face,fill=chalk)
                if mode=="blackboard" and j<len(points)-1:
                    d.line((690,y+65,690,y+86),fill=YELLOW,width=4)
                    d.polygon([(682,y+78),(690,y+89),(698,y+78)],fill=YELLOW)
        # Chalk tray and freestanding supports also work on the street/campus.
        d.rectangle((310,1040,770,1060),fill="#B58C61",outline=INK,width=4)
        d.rectangle((675,1031,715,1039),fill=chalk)
        d.line((360,1060,335,1325),fill=INK,width=9)
        d.line((720,1060,745,1325),fill=INK,width=9)
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
            d.rectangle((350,1175,730,1220),fill="#D19B61",outline=INK,width=7)
            d.line((380,1220,370,1415),fill=INK,width=12)
            d.line((700,1220,710,1415),fill=INK,width=12)
            d.ellipse((460,1130,620,1175),fill="#91A7A4",outline=INK,width=6)
            d.line((540,1000,540,1150),fill=INK,width=8)
            # An outline mask makes a single clean paper-cut bone silhouette.
            shape=Image.new("L",(W,H))
            sd=ImageDraw.Draw(shape)
            sd.rounded_rectangle((518,854,562,1065),radius=18,fill=255)
            for box in [(479,820,548,890),(535,821,604,891),
                        (479,1030,548,1100),(535,1030,604,1100)]:
                sd.ellipse(box,fill=255)
            from PIL import ImageFilter
            outline=shape.filter(ImageFilter.MaxFilter(13))
            layer.paste(INK,(0,0,W,H),outline)
            layer.paste("#F5EAD1",(0,0,W,H),shape)
            d=ImageDraw.Draw(layer)
            d.rounded_rectangle((380,1232,700,1285),radius=6,fill=PAPER,outline=INK,width=3)
            self.text(d,(540,1236),"骨頭教具・示意",32,INK,"ma")
        elif scene["speaker"]=="doctor":
            # A pointer aligned with the existing hand, not an invented arm rig.
            d.line((310,1210,480,895),fill=INK,width=11)
            d.line((310,1210,480,895),fill="#B58C61",width=5)
            d.ellipse((470,885,490,905),fill=YELLOW,outline=INK,width=3)
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
        blink=int(int(t*12)%53 in (0,1))
        step=round(local*10)/10  # Intentionally stepped cut-paper movement.
        bounce=round(math.sin(step*13)*5) if speaking and level>.08 else 0
        shot=scene["shot"]
        cast=scene["cast"]
        focus=scene["speaker"] if shot=="punch" else shot
        # One locked scale for EVERY actor in EVERY board. Focus never shrinks
        # listeners or enlarges a speaker. Shared baseline keeps feet aligned.
        positions=(-50,280,610) if len(cast)==3 else ((-80,640) if lesson["mode"]!="dialogue" else (20,550))
        layout={name:(positions[i],660,780) for i,name in enumerate(cast)}
        # Compose in a masked stage to protect the subtitle safe area.
        stage=Image.new("RGBA",(W,H))
        draw_order=list(cast)
        for name in draw_order:
            x,y,height=layout[name]
            sprite=self.character_sprite(name,height,mouth if scene["speaker"]==name else 0,
                                         blink if name!="mei" else 0)
            active=scene["speaker"]==name
            motion=scene.get("motion","nod")
            ox=bounce if active and motion=="shake" else 0
            oy=bounce if active and motion=="nod" else 0
            stage.alpha_composite(sprite,(x+ox,y+oy))
        im.paste(stage.crop((0,455,W,1470)),(0,455),stage.crop((0,455,W,1470)))
        props=self.teaching_props(scene)
        if props is not None:
            im.paste(props,(0,0),props)
        d=ImageDraw.Draw(im)
        who=self.episode["names"][scene["speaker"]]
        d.rounded_rectangle((65,1490,390,1550),radius=8,fill=CORAL if scene["speaker"]!="doctor" else "#A4D1C6",outline=INK,width=3)
        self.text(d,(84,1494),who,35)
        caption=subtitle_at(scene,t)
        cache_key=(scene["index"],caption)
        if cache_key not in self.caption_cache:
            self.caption_cache[cache_key]=fit(caption,self.font_path,66,944,2)
        face,lines=self.caption_cache[cache_key]
        for j,line in enumerate(lines):
            d.text((65,1568+j*79),line,font=face,fill=INK)
        progress=min(1,max(0,local/(scene["end"]-scene["start"])))
        d.rectangle((65,1845,1015,1857),fill="#DDD6C8")
        d.rectangle((65,1845,65+950*progress,1857),fill=INK)
        return im
