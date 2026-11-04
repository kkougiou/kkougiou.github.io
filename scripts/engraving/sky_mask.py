import cv2, numpy as np
im = cv2.imread('/home/claude/kkougiou.github.io/assets/media/hero-landscape.jpg')
hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV).astype(np.int32)
H,S,V = hsv[...,0],hsv[...,1],hsv[...,2]
sk = (((H>=95)&(H<=128)&(S>=45)&(V>=120)) | ((V>=185)&(S<=60)&(H>=90))).astype(np.uint8)
sk = cv2.morphologyEx(sk, cv2.MORPH_CLOSE, np.ones((9,9),np.uint8))
sk = cv2.morphologyEx(sk, cv2.MORPH_OPEN, np.ones((5,5),np.uint8))
n,lab = cv2.connectedComponents(sk)
top = set(np.unique(lab[0])) - {0}
m = np.isin(lab, list(top)).astype(np.uint8)
# fill holes: per column, sky = everything above the lowest sky pixel connected... use column fill
h,w = m.shape
out = np.zeros_like(m)
for x in range(w):
    ys = np.where(m[:,x])[0]
    if len(ys):
        # first gap of >=6 non-sky rows marks ridge
        y=0; col=m[:,x]
        while y<h:
            if col[y]==0 and col[y:y+6].sum()==0: break
            y+=1
        out[:y,x]=1
cv2.imwrite('skymask.png', np.hstack([im, cv2.cvtColor(out*255,cv2.COLOR_GRAY2BGR)]))
np.save('sky.npy', out)
