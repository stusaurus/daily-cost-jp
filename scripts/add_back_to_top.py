import re
from pathlib import Path

SITE = Path("site")

STYLE = '''<style id="back-to-top-style">
#back-to-top{position:fixed;right:16px;bottom:calc(env(safe-area-inset-bottom,0px) + 20px);width:50px;height:50px;border:0;border-radius:999px;background:#b3261e;color:#fff;font-size:23px;font-weight:900;line-height:1;display:grid;place-items:center;box-shadow:0 6px 18px rgba(0,0,0,.18);z-index:9999;opacity:0;visibility:hidden;transform:translateY(8px);transition:opacity .2s ease,transform .2s ease,visibility .2s;cursor:pointer;-webkit-tap-highlight-color:transparent}
#back-to-top.is-visible{opacity:.94;visibility:visible;transform:translateY(0)}
#back-to-top:active{transform:scale(.96)}
@media(min-width:900px){#back-to-top{right:max(24px,calc((100vw - 980px)/2))}}
@media(prefers-reduced-motion:reduce){#back-to-top{transition:none}}
</style>'''

BUTTON = '<button id="back-to-top" type="button" aria-label="ページ上部へ戻る" title="ページ上部へ戻る">↑</button>'

SCRIPT = '''<script id="back-to-top-script">
(function(){
  const button=document.getElementById('back-to-top');
  if(!button)return;
  const update=()=>button.classList.toggle('is-visible',window.scrollY>500);
  window.addEventListener('scroll',update,{passive:true});
  update();
  button.addEventListener('click',()=>{
    const reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({top:0,behavior:reduce?'auto':'smooth'});
  });
})();
</script>'''


def inject(path: Path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'<style id="back-to-top-style">.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<button id="back-to-top".*?</button>', '', text, flags=re.DOTALL)
    text = re.sub(r'<script id="back-to-top-script">.*?</script>', '', text, flags=re.DOTALL)

    if '</head>' in text:
        text = text.replace('</head>', STYLE + '\n</head>', 1)
    if '</body>' in text:
        text = text.replace('</body>', BUTTON + '\n' + SCRIPT + '\n</body>', 1)
    else:
        text += '\n' + BUTTON + '\n' + SCRIPT

    path.write_text(text, encoding="utf-8")


def main():
    count = 0
    for path in SITE.rglob('*.html'):
        inject(path)
        count += 1
    print(f"Added back-to-top button to {count} pages")


if __name__ == '__main__':
    main()
