"""Connected, fixed-length shoulder/elbow/wrist rigs for paper-cut gestures."""
import math
from PIL import Image, ImageDraw, ImageFilter

INK="#202332"


def arm_pose(rig,source_size,height,gesture,phase,direction=1):
    if gesture=="rest":
        return None
    wave=math.sin(phase*math.tau/6)
    if gesture=="talk":
        upper,fore=74+3*wave,28+7*wave
    elif gesture=="point":
        upper,fore=32+2*wave,-32+3*wave
    elif gesture=="present":
        upper,fore=57+3*wave,-3+4*wave
    elif gesture=="question":
        upper,fore=64+2*wave,-64+3*wave
    elif gesture=="wave":
        upper,fore=56+2*wave,-56+7*wave
    else:
        raise ValueError(f"Unsupported gesture: {gesture}")
    # Keep a visible elbow bend; never rotate a whole sleeve across the torso.
    fore=max(upper-140,min(upper-20,fore))
    side=1 if direction>0 else 0
    if side==0:
        upper,fore=180-upper,180-fore
    iw,ih=source_size
    sx,sy=rig["shoulder"]
    shoulder=((1-sx if side else sx)*iw*height/ih,sy*height)
    a,b=(value*height for value in rig["arm_lengths"])
    def advance(point,angle,length):
        theta=math.radians(angle)
        return point[0]+math.cos(theta)*length,point[1]+math.sin(theta)*length
    elbow=advance(shoulder,upper,a)
    wrist=advance(elbow,fore,b)
    hand=advance(wrist,fore,height*.022)
    return {"side":side,"shoulder":shoulder,"elbow":elbow,"wrist":wrist,
            "hand":hand,"upper_length":a,"lower_length":b,
            "upper_angle":upper,"fore_angle":fore}


def _segment(draw,a,b,wa,wb):
    dx,dy=b[0]-a[0],b[1]-a[1]
    length=math.hypot(dx,dy)
    nx,ny=-dy/length,dx/length
    draw.polygon([(a[0]+nx*wa,a[1]+ny*wa),(b[0]+nx*wb,b[1]+ny*wb),
                  (b[0]-nx*wb,b[1]-ny*wb),(a[0]-nx*wa,a[1]-ny*wa)],fill=255)


def _disc(draw,point,radius):
    x,y=point
    draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=255)


def _paint_shape(image,mask,fill):
    # One outline around the UNION, so no black cut seam runs across the elbow.
    image.paste(INK,(0,0,*image.size),mask.filter(ImageFilter.MaxFilter(7)))
    image.paste(fill,(0,0,*image.size),mask)


def draw_arm(image,pose,rig,height,pad):
    shoulder,elbow,wrist=[(pose[key][0]+pad,pose[key][1]) for key in ("shoulder","elbow","wrist")]
    mask=Image.new("L",image.size)
    d=ImageDraw.Draw(mask)
    root_width,elbow_width,wrist_width=(height*v for v in (.029,.025,.021))
    _segment(d,shoulder,elbow,root_width,elbow_width)
    _segment(d,elbow,wrist,elbow_width,wrist_width)
    _disc(d,shoulder,root_width)
    _disc(d,elbow,elbow_width)
    _disc(d,wrist,wrist_width)
    _paint_shape(image,mask,rig["sleeve_color"])
    # Cuff follows the forearm; the palm overlaps the wrist/cuff by several pixels.
    theta=math.radians(pose["fore_angle"])
    ux,uy=math.cos(theta),math.sin(theta)
    cuff_start=(wrist[0]-ux*height*.018,wrist[1]-uy*height*.018)
    cuff=Image.new("L",image.size)
    _segment(ImageDraw.Draw(cuff),cuff_start,wrist,wrist_width*1.04,wrist_width)
    _paint_shape(image,cuff,rig["cuff_color"])
    palm=Image.new("L",image.size)
    d=ImageDraw.Draw(palm)
    nx,ny=-uy,ux
    cx,cy=wrist[0]+ux*height*.022,wrist[1]+uy*height*.022
    outline=[]
    for k in range(32):
        angle=k*math.tau/32
        along=math.cos(angle)*height*.029
        across=math.sin(angle)*height*.023
        outline.append((cx+ux*along+nx*across,cy+uy*along+ny*across))
    d.polygon(outline,fill=255)
    # Small thumb lobe, connected to the palm rather than a detached hand stamp.
    thumb=(wrist[0]+ux*height*.013+nx*height*.021,
           wrist[1]+uy*height*.013+ny*height*.021)
    _disc(d,thumb,height*.012)
    _paint_shape(image,palm,rig["skin"])
    d=ImageDraw.Draw(image)
    for offset in (-.009,.003,.014):
        p=(cx+ux*height*.007+nx*height*offset,cy+uy*height*.007+ny*height*offset)
        d.line((p[0],p[1],p[0]+ux*height*.010,p[1]+uy*height*.010),fill=INK,width=2)
