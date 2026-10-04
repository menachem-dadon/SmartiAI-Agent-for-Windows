"""Original UX-1 outline icons, rasterized to transparent PNGs (no SVG/runtime font).
24-unit geometry, 1.6-unit rounded strokes, supersampled for 18-24 px controls.
All artwork below is authored for this prototype; no legacy product artwork.
"""
from pathlib import Path
from PIL import Image, ImageDraw
import math

OUT = Path(__file__).resolve().parents[1] / 'desktop/src/design-system/icons'
SCALE=12
class Pen:
 def __init__(self, color):
  self.image=Image.new('RGBA',(24*SCALE,24*SCALE)); self.d=ImageDraw.Draw(self.image); self.color=color
 def line(self,*points):
  pts=[(round(x*SCALE),round(y*SCALE)) for x,y in points]; w=round(1.6*SCALE)
  self.d.line(pts,fill=self.color,width=w,joint='curve')
  for x,y in (pts[0],pts[-1]): self.d.ellipse((x-w/2,y-w/2,x+w/2,y+w/2),fill=self.color)
 def circle(self,x,y,r): self.d.ellipse(tuple(round(v*SCALE) for v in (x-r,y-r,x+r,y+r)),outline=self.color,width=round(1.6*SCALE))
 def rect(self,x,y,w,h,r=1): self.d.rounded_rectangle(tuple(round(v*SCALE) for v in (x,y,x+w,y+h)),radius=round(r*SCALE),outline=self.color,width=round(1.6*SCALE))
 def arc(self,x,y,w,h,a,b): self.d.arc(tuple(round(v*SCALE) for v in (x,y,x+w,y+h)),a,b,fill=self.color,width=round(1.6*SCALE))
 def dot(self,x,y): self.d.ellipse(tuple(round(v*SCALE) for v in (x-.85,y-.85,x+.85,y+.85)),fill=self.color)

def draw(name,p):
 L=p.line; R=p.rect; C=p.circle; A=p.arc; D=p.dot
 if name=='plus': L((12,5),(12,19)); L((5,12),(19,12))
 elif name=='close': L((6,6),(18,18)); L((18,6),(6,18))
 elif name=='check': L((5,12),(10,17),(19,7))
 elif name in ['arrow','back','forward']:
  right=name=='forward'; L((5,12),(19,12)); L((13,6),(19,12),(13,18)) if right else L((11,6),(5,12),(11,18))
 elif name=='chevron': L((6,9),(12,15),(18,9))
 elif name=='send': L((12,20),(12,4)); L((5,11),(12,4),(19,11))
 elif name=='stop': R(6,6,12,12,2)
 elif name=='pause': L((8,5),(8,19)); L((16,5),(16,19))
 elif name=='play': L((7,4),(20,12),(7,20),(7,4))
 elif name=='mic': R(9,3,6,12,3); A(6,6,12,12,0,180); L((12,18),(12,21)); L((9,21),(15,21))
 elif name=='search': C(10,10,6); L((14.5,14.5),(20,20))
 elif name=='settings':
  pts=[]
  for i in range(48):
   a=i*math.pi/24; r=8.5 if i%8 in [2,3,4,5] else 6.6; pts.append((12+r*math.cos(a),12+r*math.sin(a)))
  L(*pts,pts[0]); C(12,12,3)
 elif name in ['file','newChat','canvas']:
  L((5,3),(14,3),(19,8),(19,21),(5,21),(5,3)); L((14,3),(14,8),(19,8))
  if name=='file': L((8,12),(16,12)); L((8,16),(14,16))
  else: L((8,16),(10,16),(17,9),(15,7),(8,14),(8,16))
 elif name=='folder': L((3,7),(3,20),(21,20),(21,7),(12,7),(9,4),(3,4),(3,7))
 elif name=='expand':
  for pts in [[(9,4),(4,4),(4,9)],[(15,4),(20,4),(20,9)],[(4,15),(4,20),(9,20)],[(15,20),(20,20),(20,15)]]: L(*pts)
 elif name=='shrink':
  for pts in [[(4,9),(9,9),(9,4)],[(15,4),(15,9),(20,9)],[(9,20),(9,15),(4,15)],[(20,15),(15,15),(15,20)]]: L(*pts)
 elif name=='archive': R(3,3,18,5); R(5,8,14,13); L((9,12),(15,12))
 elif name=='panel': R(3,4,18,16); L((15,4),(15,20))
 elif name=='copy': R(8,8,13,13); L((16,5),(16,3),(3,3),(3,16),(5,16))
 elif name in ['download','export']:
  L((12,3),(12,15)); L((7,10),(12,15),(17,10)); L((4,16),(4,21),(20,21),(20,16))
 elif name in ['shield','lock']:
  L((12,3),(20,6),(19,14),(16,19),(12,22),(8,19),(5,14),(4,6),(12,3))
  if name=='shield': L((8,12),(11,15),(16,9))
  else: R(9,11,6,5); A(9,6,6,8,180,360)
 elif name=='spark': L((12,3),(14.5,9.5),(21,12),(14.5,14.5),(12,21),(9.5,14.5),(3,12),(9.5,9.5),(12,3))
 elif name=='more':
  for y in [5,12,19]: D(12,y)
 elif name=='pin': L((8,3),(16,3),(15,9),(18,13),(6,13),(9,9),(8,3)); L((12,13),(12,21))
 elif name=='rename': L((4,17),(4,21),(8,21),(20,9),(16,5),(4,17)); L((14,7),(18,11))
 elif name=='trash': L((4,6),(20,6)); R(7,6,10,15); L((9,3),(15,3)); L((10,10),(10,17)); L((14,10),(14,17))
 elif name=='speaker': L((3,9),(7,9),(12,5),(12,19),(7,15),(3,15),(3,9)); A(12,7,6,10,290,70); A(10,3,12,18,290,70)
 elif name=='memory': R(6,6,12,12,2); R(9,9,6,6)
 elif name=='browser': R(3,3,18,18,2); L((3,8),(21,8)); D(6,5.5); D(9,5.5); C(12,14,4); L((12,10),(12,18)); L((8,14),(16,14))
 elif name=='terminal': R(3,4,18,16,2); L((7,9),(10,12),(7,15)); L((13,15),(17,15))
 elif name=='tools':
  A(2,2,11,11,50,315); L((4,4),(7,7),(10,4)); L((12,9),(21,18),(18,21),(9,12))
 elif name=='tasks': R(4,4,16,17,2); R(8,2,8,4); L((7,11),(9,13),(12,9)); L((14,11),(17,11)); L((7,17),(17,17))
 elif name=='usage': L((4,3),(4,21),(21,21)); L((8,17),(8,12)); L((13,17),(13,8)); L((18,17),(18,4))
 elif name=='activity': L((3,12),(7,12),(10,5),(14,19),(17,12),(21,12))
 elif name=='refresh': A(4,4,16,16,40,315); L((17,3),(19,7),(15,7))
 elif name=='external': L((13,3),(21,3),(21,11)); L((11,13),(21,3)); L((10,4),(4,4),(4,20),(20,20),(20,14))
 elif name=='info': C(12,12,9); L((12,11),(12,17)); D(12,7)
 elif name in ['star','starFilled']:
  pts=[(12+(9 if i%2==0 else 4)*math.cos(-math.pi/2+i*math.pi/5),12+(9 if i%2==0 else 4)*math.sin(-math.pi/2+i*math.pi/5)) for i in range(10)]
  L(*pts,pts[0]);
  if name=='starFilled': p.d.polygon([(x*SCALE,y*SCALE) for x,y in pts],fill=p.color)
 elif name=='save': L((3,3),(17,3),(21,7),(21,21),(3,21),(3,3)); R(7,3,9,6); R(7,14,10,7)
 elif name=='wrap': L((4,6),(20,6)); L((4,11),(16,11)); A(13,11,7,7,270,90); L((16,18),(8,18)); L((11,15),(8,18),(11,21))
 elif name=='user': C(12,7,4); A(4,13,16,16,180,360)
 elif name=='sun':
  C(12,12,4)
  for i in range(8):
   a=i*math.pi/4; L((12+7*math.cos(a),12+7*math.sin(a)),(12+10*math.cos(a),12+10*math.sin(a)))
 elif name=='moon':
  outer=[(12+9*math.cos(math.radians(a)),12+9*math.sin(math.radians(a))) for a in range(3,268,3)]
  inner=[(18+7*math.cos(math.radians(a)),6+7*math.sin(math.radians(a))) for a in range(205,64,-3)]
  L(*outer,*inner,outer[0])
 elif name=='home': L((3,10),(12,3),(21,10)); L((5,9),(5,21),(19,21),(19,9)); R(10,14,4,7)
 elif name=='alert': L((12,3),(22,21),(2,21),(12,3)); L((12,9),(12,14)); D(12,17)
 elif name=='loader': A(3,3,18,18,20,290)
 elif name=='history': C(12,12,9); L((12,6),(12,12),(16,14))
 elif name=='mail': R(3,5,18,14,2); L((3,6),(12,13),(21,6))
 elif name=='screen': R(3,3,18,14,2); L((12,17),(12,21)); L((7,21),(17,21))
 elif name=='code': L((8,6),(3,12),(8,18)); L((16,6),(21,12),(16,18)); L((14,3),(10,21))
 elif name=='globe': C(12,12,9); p.d.ellipse((8*SCALE,3*SCALE,16*SCALE,21*SCALE),outline=p.color,width=round(1.6*SCALE)); L((3,12),(21,12))
 elif name=='bell': L((4,17),(6,14),(6,8),(8,4),(12,3),(16,4),(18,8),(18,14),(20,17),(4,17)); A(9,17,6,5,0,180)
 elif name=='layers': L((3,7),(12,2),(21,7),(12,12),(3,7)); L((3,12),(12,17),(21,12)); L((3,17),(12,22),(21,17))
 elif name=='plug': L((8,2),(8,7)); L((16,2),(16,7)); L((5,7),(19,7)); A(5,3,14,14,0,180); L((12,17),(12,22))
 elif name=='paste': R(4,4,16,17,2); R(8,2,8,5); L((8,12),(16,12)); L((8,16),(14,16))
 elif name=='book': L((12,5),(7,3),(3,3),(3,19),(7,19),(12,21),(17,19),(21,19),(21,3),(17,3),(12,5),(12,21))
 else: raise ValueError(name)
 if name=='memory':
  for a in [8,12,16]: L((a,3),(a,5)); L((a,19),(a,21)); L((3,a),(5,a)); L((19,a),(21,a))

NAMES='plus close check arrow back forward chevron send stop pause play mic search settings file newChat canvas folder expand panel copy download export shield lock spark more pin rename trash speaker memory browser terminal tools tasks usage activity refresh external info star starFilled save wrap user sun moon home history mail screen code globe bell layers plug paste book alert loader'.split()
OUT.mkdir(parents=True,exist_ok=True)
NAMES += ['shrink', 'archive']
for theme,color in [('light','#303947'),('dark','#edf0f5')]:
 for name in NAMES:
  p=Pen(color); draw(name,p); p.image.resize((72,72),Image.Resampling.LANCZOS).save(OUT / f'{name}-{theme}.png',optimize=True)
print(f'Generated {len(NAMES)*2} original PNG icons')
