"""Multi-layout editable PowerPoint renderer."""
from pathlib import Path
from io import BytesIO
import re, threading, requests
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR

LOCK=threading.Lock()
PALETTES={
"dark":(RGBColor(12,18,32),RGBColor(24,34,54),RGBColor(31,45,70),RGBColor(102,183,255),RGBColor(246,248,252),RGBColor(174,188,210),RGBColor(123,226,191)),
"academic":(RGBColor(250,247,239),RGBColor(255,255,255),RGBColor(238,231,216),RGBColor(38,83,112),RGBColor(37,43,49),RGBColor(104,109,111),RGBColor(73,124,93)),
"minimal":(RGBColor(248,249,251),RGBColor(255,255,255),RGBColor(235,239,244),RGBColor(39,91,140),RGBColor(30,38,48),RGBColor(100,112,125),RGBColor(38,125,103)),
"colorful":(RGBColor(29,20,56),RGBColor(47,34,81),RGBColor(67,47,105),RGBColor(255,112,92),RGBColor(255,250,247),RGBColor(218,204,230),RGBColor(111,222,190)),
"classic":(RGBColor(250,247,239),RGBColor(255,255,255),RGBColor(238,231,216),RGBColor(38,83,112),RGBColor(37,43,49),RGBColor(104,109,111),RGBColor(73,124,93))}
def bg(s,c): s.background.fill.solid(); s.background.fill.fore_color.rgb=c
def box(s,x,y,w,h,c,rounded=True):
 sh=s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE, Inches(x),Inches(y),Inches(w),Inches(h)); sh.fill.solid(); sh.fill.fore_color.rgb=c; sh.line.fill.background(); return sh
def txt(s,v,x,y,w,h,size=16,c=None,bold=False,italic=False,margin=.07):
 sh=s.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h)); tf=sh.text_frame; tf.clear(); tf.word_wrap=True; tf.vertical_anchor=MSO_ANCHOR.TOP; tf.margin_left=tf.margin_right=Inches(margin); tf.margin_top=tf.margin_bottom=Inches(margin); p=tf.paragraphs[0]; p.text=str(v or ""); p.font.name="Aptos"; p.font.size=Pt(size); p.font.bold=bold; p.font.italic=italic
 if c:p.font.color.rgb=c
 return sh
def image(s,item,x,y,w,h):
 try:
  r=requests.get(item.get("image_url",""),timeout=8,headers={"User-Agent":"PresentMaker/2"}); r.raise_for_status()
  if len(r.content)>12_000_000:return False
  pic=s.shapes.add_picture(BytesIO(r.content),Inches(x),Inches(y),width=Inches(w),height=Inches(h))
  iw,ih=pic.image.size; ratio=w/h; sr=iw/ih
  if sr>ratio: crop=(1-ratio/sr)/2; pic.crop_left=pic.crop_right=crop
  elif sr<ratio: crop=(1-sr/ratio)/2; pic.crop_top=pic.crop_bottom=crop
  return True
 except Exception:return False
def body_of(item):
 body=str(item.get("body") or "").strip()
 if not body and item.get("bullets"): body="\n".join("• "+str(v) for v in item["bullets"])
 if not body: body="\n\n".join(str(item.get(k,"")).strip() for k in ("example","takeaway","highlight") if str(item.get(k,"")).strip())
 if not body: raise ValueError("A slide has no content.")
 return body
def layout_of(item,i):
 v=str(item.get("layout") or item.get("visual") or "").lower()
 aliases={"diagram":"cards","comparison":"compare","conclusion":"closing","stats":"stats"}
 v=aliases.get(v,v)
 if v in ("cards","image","compare","timeline","quote","stats","closing","split"):return v
 return ["split","cards","image","compare"][i%4]
def cover(prs,topic,content,imgs,p):
 B,P,P2,A,T,M,G=p;s=prs.slides.add_slide(prs.slide_layouts[6]);bg(s,B);box(s,.65,.65,.12,6.15,A,False);txt(s,"PRESENT-MAKER / STUDY",1.05,.85,6,.4,11,G,True);txt(s,content.get("title") or topic,1.05,1.65,7.1,2.8,35,T,True);txt(s,content.get("subtitle") or "Research-based explanatory presentation",1.08,4.6,6.8,1,18,M);box(s,8.35,.65,4.3,6.15,P)
 if not imgs or not image(s,imgs[0],8.6,.95,3.8,3.1): box(s,9.1,1.5,2.5,2.5,P2);box(s,9.8,2.2,1.4,1.4,A)
 txt(s,"LECTURE • EXPLAIN • EXPLORE",8.65,4.55,3.6,.4,10,A,True);txt(s,"Generated research notes",8.65,5.05,3.5,.7,16,T)
def header(s,item,i,p):
 B,P,P2,A,T,M,G=p;txt(s,f"SECTION {i+1:02d}",.82,.48,2.8,.3,10,G,True);txt(s,item.get("title","Key idea"),.82,.88,11.65,1.05,27,T,True);box(s,.82,1.95,.72,.045,A,False)
def split(s,item,b,imgs,i,p):
 B,P,P2,A,T,M,G=p;box(s,.78,2.25,7.1,4.45,P);txt(s,b,.98,2.48,6.72,4,15,T);box(s,8.12,2.25,4.42,4.45,P2);img=imgs[(i+1)%len(imgs)] if imgs else None;y=2.55
 if img and image(s,img,8.38,2.48,3.92,2.35): y=5.05
 else:txt(s,str(item.get("visual","CORE IDEA")).upper(),8.45,2.68,3.8,.5,13,A,True);y=3.5
 ex=str(item.get("example","")).strip();take=str(item.get("takeaway") or item.get("highlight") or "")
 if ex:txt(s,"EXAMPLE",8.45,y,3.8,.25,9,G,True);txt(s,ex,8.45,y+.32,3.75,1,11,T);y+=1.35
 if take:txt(s,"KEY TAKEAWAY",8.45,y,3.8,.25,9,A,True);txt(s,take,8.45,y+.32,3.75,.85,11,T,True)
def cards(s,item,b,p):
 B,P,P2,A,T,M,G=p; items=item.get("bullets") or [v.strip() for v in re.split(r"\n+|(?<=[.!?])\s+",b) if v.strip()];items=items[:4] or [b];cols=2 if len(items)>2 else len(items);cw=(11.7-(cols-1)*.28)/cols;ch=2
 for i,v in enumerate(items):
  x=.82+(i%cols)*(cw+.28);y=2.25+(i//cols)*(ch+.25);box(s,x,y,cw,ch,P);box(s,x+.22,y+.22,.52,.04,A,False);txt(s,f"{i+1:02d}",x+.24,y+.42,.6,.4,14,G,True);txt(s,v,x+.24,y+.88,cw-.48,ch-.94,14,T)
 take=str(item.get("takeaway") or item.get("highlight") or "")
 if take:box(s,.82,6.55,11.7,.38,P2);txt(s,take,.98,6.59,11.3,.26,10,A,True)
def compare(s,item,b,p):
 B,P,P2,A,T,M,G=p;parts=[str(v) for v in (item.get("bullets") or re.split(r"\n+|(?<=[.!?])\s+",b)) if str(v).strip()][:2]
 while len(parts)<2:parts.append(b)
 for i,v in enumerate(parts):x=.82+i*5.92;box(s,x,2.25,5.72,4.45,P if i==0 else P2);txt(s,"SIDE "+str(i+1),x+.3,2.55,4.9,.35,10,A if i==0 else G,True);txt(s,v,x+.3,3,5,3.2,16,T,True)
 take=str(item.get("takeaway") or item.get("highlight") or "")
 if take:txt(s,take,.95,6.72,11.3,.28,11,A,True)
def timeline(s,item,b,p):
 B,P,P2,A,T,M,G=p;items=item.get("bullets") or [v.strip() for v in b.splitlines() if v.strip()];items=items[:5];box(s,1.15,3.8,10.9,.05,A,False);space=10.9/max(1,len(items))
 for i,v in enumerate(items):
  x=1.15+i*space;box(s,x,3.72,.22,.22,A);y=2.5 if i%2==0 else 4.4;box(s,x-.18,y,.12,1,G if i%2 else A,False);txt(s,v,x+.12,y,space-.25,1.35,12,T,True)
def quote(s,item,b,p):
 B,P,P2,A,T,M,G=p;box(s,.82,2.25,11.7,4.45,P);txt(s,"“",1.2,2.55,1,.8,44,A,True);txt(s,item.get("quote") or b,1.8,3,9.4,2.7,24,T,True,True);txt(s,item.get("author",""),1.8,5.85,8,.4,12,G,True)
def stats(s,item,b,p):
 B,P,P2,A,T,M,G=p;metrics=item.get("metrics") or [{"label":"Main point","value":str(item.get("takeaway") or b[:80])}];metrics=metrics[:3];w=11.7/len(metrics)
 for i,m in enumerate(metrics):x=.82+i*w;box(s,x,2.25,w-.2,2.65,P);txt(s,m.get("value",""),x+.25,2.65,w-.6,1,24,A,True);txt(s,m.get("label",""),x+.25,3.8,w-.6,.75,13,T)
 box(s,.82,5.15,11.7,1.55,P2);txt(s,b,.98,5.35,11.35,1.1,13,T)
def image_layout(s,item,b,imgs,i,p):
 B,P,P2,A,T,M,G=p;box(s,.82,2.25,4.15,4.45,P);txt(s,b,1.02,2.5,3.75,3.9,14,T);box(s,5.2,2.25,7.35,4.45,P2);img=imgs[(i+1)%len(imgs)] if imgs else None
 if img and image(s,img,5.42,2.48,6.9,3.5):txt(s,img.get("title","Illustration"),5.45,6.1,6.7,.35,9,M)
 else:box(s,6.05,3,2.1,2.1,A);box(s,8.05,4,2,1.5,G);txt(s,str(item.get("visual","VISUAL SUMMARY")).upper(),5.55,5.8,6.6,.4,12,T,True)
def closing(s,item,b,p):
 B,P,P2,A,T,M,G=p;box(s,.82,2.25,11.7,4.45,P);txt(s,"CONCLUSION",1.2,2.62,3,.4,11,G,True);txt(s,b,1.2,3.2,9.9,2.5,23,T,True);take=str(item.get("takeaway") or item.get("highlight") or "")
 if take:txt(s,take,1.2,5.8,9.9,.6,13,A)
def footer(s,n,total,p):
 B,P,P2,A,T,M,G=p;box(s,.72,7.05,.42,.035,A,False);txt(s,"PRESENT-MAKER",.78,7.12,2.5,.18,8,M,True,margin=0);txt(s,f"{n:02d} / {total:02d}",11.65,7.08,1,.22,9,M,margin=0)
def sources_slide(prs,sources,p):
 B,P,P2,A,T,M,G=p;s=prs.slides.add_slide(prs.slide_layouts[6]);bg(s,B);txt(s,"Sources & further reading",.82,.65,11.6,.8,28,T,True);txt(s,"Reading status is an extraction label, not independent verification.",.85,1.5,11.4,.45,11,M);y=2.05
 for i,src in enumerate(sources[:14],1):
  if y>.6+6.2:break
  txt(s,f"[S{i}] {src.get('title','Source')} · {src.get('read_status','status unknown')}",.95,y,11.1,.28,10,T,True);txt(s,str(src.get("url",""))[:170],.95,y+.3,11.1,.24,8,A);y+=.65
 footer(s,len(prs.slides),len(prs.slides),p)
def create_pptx(topic,lang,content,sources,output_path,settings=None):
 settings=settings or {}
 with LOCK:return render(topic,lang,content,sources,output_path,settings)
def render(topic,lang,content,sources,output_path,settings):
 p=PALETTES.get(settings.get("style","dark"),PALETTES["dark"]);B,P,P2,A,T,M,G=p;prs=Presentation();prs.slide_width=Inches(13.333);prs.slide_height=Inches(7.5);items=content.get("slides") or []
 if not items:raise ValueError("AI returned no slides.")
 imgs=[src for src in sources if src.get("source_type")=="image"];cover(prs,topic,content,imgs,p)
 for i,item in enumerate(items):
  s=prs.slides.add_slide(prs.slide_layouts[6]);bg(s,B);header(s,item,i,p);b=body_of(item);l=layout_of(item,i)
  if l=="cards":cards(s,item,b,p)
  elif l=="compare":compare(s,item,b,p)
  elif l=="timeline":timeline(s,item,b,p)
  elif l=="quote":quote(s,item,b,p)
  elif l=="stats":stats(s,item,b,p)
  elif l=="image":image_layout(s,item,b,imgs,i,p)
  elif l=="closing":closing(s,item,b,p)
  else:split(s,item,b,imgs,i,p)
  notes=str(item.get("speaker_notes","")).strip()
  if notes:
   try:s.notes_slide.notes_text_frame.text=notes
   except Exception:pass
  ev=item.get("evidence",[])
  if ev:txt(s,"Sources: "+", ".join(map(str,ev)),.82,6.78,9.5,.2,8,M,margin=0)
  footer(s,i+1,len(items),p)
 sources_slide(prs,sources,p);output_path=Path(output_path);output_path.parent.mkdir(parents=True,exist_ok=True);prs.save(output_path);return output_path
