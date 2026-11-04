import cv2, numpy as np
im = cv2.imread('/home/claude/kkougiou.github.io/assets/media/hero-landscape.jpg')
m = np.load('sky.npy'); h,w=m.shape
ridge = np.array([np.argmin(m[:,x]) if m[:,x].min()==0 else h for x in range(w)],float)
pts = np.array([(0,62),(40,80),(100,115),(160,150),(230,195),(300,240),(350,268),(390,292),(420,305),(445,306)])
xs=np.arange(w); left = np.interp(xs, pts[:,0], pts[:,1])
ridge = np.where(xs<445, left, ridge)
ridge = np.convolve(np.pad(ridge,4,mode='edge'),np.ones(9)/9,'valid')
np.save('ridge.npy', ridge)
v = im.copy()
for x in range(w-1): cv2.line(v,(x,int(ridge[x])),(x+1,int(ridge[x+1])),(0,0,255),2)
cv2.imwrite('ridge.jpg', v)
