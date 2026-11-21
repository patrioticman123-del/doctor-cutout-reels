"""Full-bleed 1080x1920 sets. Titles and review notes live outside the frame."""
from PIL import Image, ImageDraw

W,H=1080,1920
INK="#202332"


def draw_scene(scene,text):
    setting=scene["setting"]
    im=Image.new("RGB",(W,H),"#E7C995")
    d=ImageDraw.Draw(im)
    if setting=="classroom":
        d.rectangle((0,0,W,1390),fill="#E7C995")
        d.rectangle((0,1390,W,H),fill="#C79C75")
        for x in (-250,200,650,1100):
            d.line((540+(x-540)*.45,1390,x,H),fill="#A77B5B",width=5)
        for y in (1510,1680,1900):
            d.line((0,y,W,y),fill="#A77B5B",width=4)
        if scene.get("teaching",{}).get("mode","dialogue")=="dialogue":
            d.rectangle((55,170,755,700),fill="#855D48",outline=INK,width=9)
            d.rectangle((75,190,735,675),fill="#315D57",outline=INK,width=5)
            text(d,(115,255),"今天的健康課",57,"#F7F0CF")
            d.line((115,370,620,370),fill="#D5DEBE",width=5)
            d.rectangle((45,700,765,724),fill="#B58C61",outline=INK,width=5)
        d.rectangle((805,150,1045,740),fill="#FCF3DB",outline=INK,width=8)
        d.rectangle((825,170,1025,720),fill="#9ACACC")
        d.line((925,170,925,720),fill=INK,width=6)
        d.line((825,440,1025,440),fill=INK,width=6)
        for x in (20,450,865):
            d.polygon([(x,1240),(x+180,1240),(x+210,1300),(x-25,1300)],fill="#D49353",outline=INK,width=6)
            d.line((x,1300,x-10,1500),fill=INK,width=10)
            d.line((x+180,1300,x+190,1500),fill=INK,width=10)
    elif setting=="schoolyard":
        d.rectangle((0,0,W,H),fill="#A9D2DA")
        for x,y in ((90,70),(730,160)):
            d.ellipse((x,y,x+230,y+95),fill="#FFF9ED")
        d.rectangle((55,480,1030,1330),fill="#E4BD87",outline=INK,width=9)
        d.polygon([(10,480),(545,240),(1070,480)],fill="#577F79",outline=INK,width=9)
        text(d,(545,505),"青禾小學",62,INK,"ma")
        for x in (110,300,710,895):
            for y in (700,1010):
                d.rectangle((x,y,x+100,y+165),fill="#A6CDCE",outline=INK,width=7)
                d.line((x+50,y,x+50,y+165),fill=INK,width=4)
        d.rectangle((465,1030,630,1330),fill="#755747",outline=INK,width=8)
        d.rectangle((0,1320,W,H),fill="#8EB283")
        d.polygon([(460,1320),(630,1320),(1030,H),(45,H)],fill="#D6CEB9")
        for x in (-60,980):
            d.rectangle((x+40,1080,x+65,1440),fill="#80614D")
            d.ellipse((x-70,850,x+165,1160),fill="#57846A",outline=INK,width=7)
    else:
        d.rectangle((0,0,W,H),fill="#AFCEDA")
        for x,y in ((80,100),(730,210)):
            d.ellipse((x,y,x+240,y+95),fill="#FFF9ED")
        for x,color,roof in [(-60,"#D6B5B9","#665D7D"),(375,"#E5CA94","#6B8D7E"),(810,"#B3C5AC","#9B6A60")]:
            d.rectangle((x,670,x+350,1380),fill=color,outline=INK,width=8)
            d.polygon([(x-25,670),(x+175,430),(x+375,670)],fill=roof,outline=INK,width=8)
            d.rectangle((x+40,800,x+140,1000),fill="#C6DFD8",outline=INK,width=6)
            d.rectangle((x+205,1110,x+300,1380),fill="#735E56",outline=INK,width=6)
        d.rectangle((0,1380,W,1730),fill="#D3CAB9",outline=INK,width=6)
        for x in (140,450,760,1070):
            d.line((x,1380,x-110,1730),fill="#B4AB9D",width=4)
        d.rectangle((0,1730,W,H),fill="#686D78")
        for x in range(0,W,230):
            d.rectangle((x,1845,x+125,1860),fill="#F5E7AA")
    return im
