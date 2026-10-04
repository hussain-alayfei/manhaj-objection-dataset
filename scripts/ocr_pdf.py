"""Optional local OCR sidecar; never silently replaces original extraction."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

p=argparse.ArgumentParser();p.add_argument('pdf');p.add_argument('--output',default='data/processed/ocr-pages.json');p.add_argument('--pages',nargs='*',type=int);args=p.parse_args()
if not shutil.which('tesseract'):raise SystemExit('Install Tesseract and Arabic ara.traineddata, then retry. No OCR was performed.')
import pypdfium2
pdf=pypdfium2.PdfDocument(args.pdf);result={}
with tempfile.TemporaryDirectory() as folder:
    for i in args.pages or range(1,len(pdf)+1):
        page=pdf[i-1];bitmap=page.render(scale=3);image=bitmap.to_pil();path=Path(folder)/f'page-{i}.png';image.save(path)
        cmd=['tesseract',str(path),'stdout','-l','ara','--psm','3']
        run=subprocess.run(cmd,capture_output=True,check=True,timeout=120)
        result[str(i)]=run.stdout.decode('utf-8')
        bitmap.close();page.close()
pdf.close()
output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Saved {len(result)} unverified OCR pages to {output}')
