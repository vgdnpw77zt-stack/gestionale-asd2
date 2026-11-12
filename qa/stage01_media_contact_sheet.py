"""Inspect only public already-published BodyMind photos; no writes to production."""
import json
from pathlib import Path
from urllib.request import urlopen,Request
from io import BytesIO
from PIL import Image,ImageDraw,ImageFont,ImageOps

out=Path("evidence/stage01/media");out.mkdir(parents=True,exist_ok=True)
base="https://bodymindaerialstudio.life"
sources=[("logo",base+"/seed-media/logo?v=9"),
         ("hero-static",base+"/static/media/bodymind-hero.webp"),
         ("competition",base+"/static/media/bodymind-competition-double.webp")]
sources +=[(f"gallery{i}",base+f"/seed-media/gallery{i}?v=9") for i in range(1,7)]
photo_cards=[];info=[]
for name,url in sources:
 item={"name":name}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 BodyMind QA image review"}),timeout=20) as resp:content=resp.read(12_000_000)
  im=Image.open(BytesIO(content)).convert("RGB")
  item.update({"w":im.width,"h":im.height,"bytes":len(content)})
  card=Image.new("RGB",(280,370),"#111921")
  thumb=ImageOps.contain(im,(268,318))
  card.paste(thumb,((280-thumb.width)//2,(328-thumb.height)//2))
  dr=ImageDraw.Draw(card);dr.text((10,331),name,fill="#f6e8d8")
  dr.text((10,347),f"{im.width} x {im.height}  /  {len(content)//1024} KB",fill="#d0b7a1")
  photo_cards.append(card)
 except Exception as e:item["error"]=type(e).__name__
 info.append(item)
cols=3;rows=(len(photo_cards)+cols-1)//cols
sheet=Image.new("RGB",(cols*280,rows*370),"#090e16")
for i,card in enumerate(photo_cards):sheet.paste(card,((i%cols)*280,(i//cols)*370))
sheet.save(out/"originals-contact-sheet.jpg",quality=90,optimize=True)
(out/"meta.json").write_text(json.dumps(info,indent=2))
print("BODYMIND_ORIGINAL_MEDIA "+json.dumps(info))
