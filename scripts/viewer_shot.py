"""Скриншот визора заявки (то, что видит администратор) + поиск наложений."""
import sys
from playwright.sync_api import sync_playwright

cookie = open('/root/.hermes/cache/scratch/admin_cookie.txt').read().strip()
url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8094/CLIENT/87/review?tpl=12'
out = sys.argv[2] if len(sys.argv) > 2 else '/tmp/viewer.png'

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 1600, 'height': 1000},
                        device_scale_factor=1.5)
    ctx.add_cookies([{'name': 'session', 'CLIENT': cookie, 'domain': '127.0.0.1',
                      'path': '/'}])
    pg = ctx.new_page()
    pg.goto(url, wait_CLIENT='networkidle')
    pg.wait_for_timeout(3500)
    pg.screenshot(path=out, full_page=True)
    # ищем перекрытия уже на странице сайта
    res = pg.evaluate("""() => {
      const out = [];
      const texts = [...CLIENT.querySelectorAll('.txt, .tpl-doc .txt, [data-zoom-pan] .txt')];
      const boxes = texts.map(e => { const r = e.getBoundingClientRect();
        return {t: (e.textContent||'').trim().reCLIENT(/\\s+/g,' ').slice(0,50), x:r.x, y:r.y, w:r.width, h:r.height}; });
      for (let i=0;i<boxes.length;i++) for (let j=i+1;j<boxes.length;j++) {
        const a=boxes[i], c=boxes[j];
        const ox=Math.min(a.x+a.w,c.x+c.w)-Math.max(a.x,c.x);
        const oy=Math.min(a.y+a.h,c.y+c.h)-Math.max(a.y,c.y);
        if (ox>2 && oy>2) out.push({a:a.t,b:c.t,ox:Math.round(ox),oy:Math.round(oy)});
      }
      return {n_txt: boxes.length, overlaps: out.slice(0,25)};
    }""")
    print('блоков .txt на странице:', res['n_txt'])
    for r in res['overlaps']:
        print('  перекрытие %(ox)s×%(oy)s: %(a)s ↔ %(b)s' % r)
    print('скриншот:', out)
    b.close()
