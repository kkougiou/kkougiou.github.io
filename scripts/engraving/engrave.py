import cv2, numpy as np, sys
SRC='/home/claude/kkougiou.github.io/assets/media/hero-landscape.jpg'
W=2400
im=cv2.imread(SRC); h0,w0=im.shape[:2]
s=W/w0; Hh=int(h0*s)
ridge=np.load('ridge.npy'); tree0=np.load('tree.npy').astype(np.float32)
big=cv2.resize(im,(W,Hh),interpolation=cv2.INTER_CUBIC)
Y,X=np.mgrid[0:Hh,0:W].astype(np.float32)
rbig=np.interp(np.arange(W)/s,np.arange(w0),ridge)*s
sky=cv2.GaussianBlur((Y<rbig[None,:]).astype(np.float32),(0,0),1.5)
tree=cv2.GaussianBlur(cv2.resize(tree0,(W,Hh),interpolation=cv2.INTER_LINEAR),(0,0),3)
smooth=cv2.bilateralFilter(big,9,40,9)
gray=cv2.cvtColor(smooth,cv2.COLOR_BGR2GRAY).astype(np.float32)/255
base=cv2.GaussianBlur(gray,(0,0),60); gray=np.clip(base+(gray-base)*1.4,0,1)
L=cv2.GaussianBlur(gray,(0,0),2.0)
P=float(sys.argv[1]) if len(sys.argv)>1 else 8.0
form=cv2.GaussianBlur(gray,(0,0),22)
rng=np.random.default_rng(7)
def nz(sig): 
    n=cv2.GaussianBlur(rng.random((Hh,W)).astype(np.float32),(0,0),sig); return (n-n.min())/(n.max()-n.min())
def lines(theta,period,width,warp):
    t=np.deg2rad(theta)
    u=(Y*np.cos(t)+X*np.sin(t))+warp
    f=np.abs(((u/period)%1.0)-0.5)*period
    half=width*period/2
    return np.clip(half-f+0.5,0,1)*np.clip(half*2.5,0,1)
# ---- rock & ground
Dr=np.clip((0.84-L)/0.84,0,1)**1.55*(1-sky)*(1-tree)
l1=lines(-16,P,np.clip(Dr*1.0,0,0.8),3.2*form*P)
l2=lines(38,P*1.1,np.clip((Dr-0.42)/0.58,0,1)*0.65,1.2*form*P)
l3=lines(-66,P*1.2,np.clip((Dr-0.72)/0.28,0,1)*0.55,0.5*form*P)
dash=nz(3.0)
l1=l1*np.clip(Dr*5.0-dash*1.3+0.25,0,1)
rock=np.maximum.reduce([l1,l2,l3])
# ---- tree foliage: clumps follow local light, short strokes
Lt=cv2.GaussianBlur(gray,(0,0),2.5)
vals=Lt[tree>0.5]; lo,hi=np.percentile(vals,4),np.percentile(vals,96)
Ln=np.clip((Lt-lo)/(hi-lo+1e-6),0,1)
Dt=(0.30+0.62*(1-Ln)**1.3)*tree
clump=cv2.GaussianBlur(gray,(0,0),6)
wob=(clump-clump.mean())*P*7+(nz(2.5)-0.5)*P*1.5
f1=lines(64,P*0.8,Dt*0.85,wob)
f2=lines(-24,P*0.85,np.clip((Dt-0.62)/0.3,0,1)*0.7,wob*0.7)
fol=np.maximum(f1,f2)*np.clip(Dt*4-nz(2.0)*0.9,0,1)
# ---- contours
g1=cv2.GaussianBlur(gray,(0,0),1.4); g2=cv2.GaussianBlur(gray,(0,0),2.6)
edges=np.clip((-(g1-g2)-0.02)/0.03,0,1)*(1-sky)*(1-tree)
tm=(cv2.GaussianBlur(tree,(0,0),5)>0.5).astype(np.uint8)
tedge=cv2.GaussianBlur((cv2.dilate(tm,np.ones((3,3)))-cv2.erode(tm,np.ones((3,3)))).astype(np.float32),(0,0),0.8)
tedge=tedge*(1-sky)
rl=np.clip(1.6-np.abs(Y-rbig[None,:])/1.3,0,1)
ink=np.maximum.reduce([rock,fol,edges*0.8,np.clip(tedge*1.5,0,1)*0.9,rl*0.9])
np.save('ink3.npy',ink)
def comp(ink,inkc,paper,name):
    p=np.array(paper,np.float32)[None,None,:]; c=np.array(inkc,np.float32)[None,None,:]
    o=p*(1-ink[...,None])+c*ink[...,None]; cv2.imwrite(name,o.astype(np.uint8))
comp(ink,(48,63,23),(239,243,238),'p6_green.png')
a=cv2.imread('p6_green.png'); cv2.imwrite('p6_small.jpg',cv2.resize(a,(1200,int(1200*Hh/W)),interpolation=cv2.INTER_AREA)); cv2.imwrite('p6_zoom.jpg',a[800:1400,1300:2200])

from PIL import Image
y0,y1=int(Hh*0.10),int(Hh*0.80)
a=ink[y0:y1]
hh=a.shape[0]; yy=np.arange(hh,dtype=np.float32)[:,None]
fade=np.clip(yy/(hh*0.20),0,1); fade=fade*fade*(3-2*fade)
a=a*fade
a=cv2.resize(a,(2000,int(2000*hh/W)),interpolation=cv2.INTER_AREA)
A=(np.clip(a,0,1)*255).astype(np.uint8)
rgba=np.zeros(A.shape+(4,),np.uint8); rgba[...,3]=A
Image.fromarray(rgba,'RGBA').save('footer-engraving.webp',quality=82,alpha_quality=80,method=6)
Image.fromarray(rgba,'RGBA').resize((1000,int(1000*A.shape[0]/2000)),Image.LANCZOS).save('footer-engraving-1000.webp',quality=82,alpha_quality=80,method=6)
print(A.shape)
