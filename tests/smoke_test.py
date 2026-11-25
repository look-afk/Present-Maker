"""Offline smoke test for JSON parsing and multi-layout PPTX export."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ai.client import extract_json
from presentation.export import create_pptx
def main():
 parsed=extract_json('{"title":"Test","slides":[{"title":"A"}]}')
 assert parsed["title"]=="Test"
 out=Path("smoke_test_output.pptx")
 slides=[
 {"title":"Core idea","body":"A paragraph explaining context and implications.","visual":"diagram","example":"A concrete example."},
 {"title":"Cards","bullets":["First component","Second component","Third component"],"layout":"cards"},
 {"title":"Visual","body":"Visual overview explanation.","layout":"image"},
 {"title":"Compare","bullets":["Option A","Option B"],"layout":"compare"},
 {"title":"Timeline","bullets":["Beginning","Middle","End"],"layout":"timeline"},
 {"title":"Summary","body":"Overall conclusion.","layout":"closing"}]
 create_pptx("Test", "en",{"title":"Test presentation","subtitle":"Offline test","slides":slides},[],out,{"style":"academic"})
 assert out.exists() and out.stat().st_size>1000
 from pptx import Presentation
 assert len(Presentation(out).slides)==len(slides)+2
 out.unlink()
 print("OK: JSON parsing and multi-layout PPTX generation")
if __name__=="__main__":main()
