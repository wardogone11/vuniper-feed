"""Vuniper -> RSS + Radarr list. Usage: python vuniper_feed.py [section ...] [--out DIR]
Sections: web gems upcoming theaters popular bluray anime top100 (default: web)
Writes vuniper-<section>.xml (RSS 2.0 for feed readers) and vuniper-<section>.json
(StevenLu format: Radarr > Import Lists > "StevenLu Custom" reads it)."""
import json, os, sys, urllib.request, email.utils, datetime
from xml.sax.saxutils import escape

API = 'https://api.vuniper.workers.dev/?action=GET_MANY_ITEMS_KV&kvName=movies_'
SECTIONS = ('web', 'gems', 'upcoming', 'theaters', 'popular', 'bluray', 'anime', 'top100')
NAMES = {'web': 'New on digital', 'gems': 'Hidden gems', 'upcoming': 'Upcoming', 'theaters': 'In theaters',
         'popular': 'Popular', 'bluray': 'New on Blu-ray', 'anime': 'Anime', 'top100': 'Top 100'}

def fetch(section):
    # the API answers 403 without the site's Origin header
    req = urllib.request.Request(API + section, headers={
        'Origin': 'https://vuniper.com', 'Referer': 'https://vuniper.com/movies',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'})
    d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    if not d.get('ok'): raise SystemExit(f'vuniper {section}: {d}')
    return d['items']

def rfc822(s):
    if not s: return None
    dt = datetime.datetime.fromisoformat(s.replace('Z', '')).replace(tzinfo=datetime.timezone.utc)
    return email.utils.format_datetime(dt)

def item_date(m, section):
    return m.get(section) if section in ('web', 'bluray') and m.get(section) else m.get('release_date') or m.get('web')

def rss(section, items):
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>',
           f'<title>Vuniper - {escape(NAMES[section])}</title>', '<link>https://vuniper.com/movies</link>',
           f'<description>Vuniper movies: {escape(NAMES[section])}</description>',
           f'<lastBuildDate>{email.utils.format_datetime(datetime.datetime.now(datetime.timezone.utc))}</lastBuildDate>']
    for m in items:
        title = f"{m['title']} ({m.get('year') or '?'})"
        bits = [f"Score {m['score']} ({m.get('reviews_count') or 0} reviews)" if m.get('score') is not None else '',
                m.get('genres') or '', m.get('runtime') if (m.get('runtime') or '').startswith(('1', '2', '3')) and 'h' in (m.get('runtime') or '') else '',
                f"Director: {m['director']}" if m.get('director') else '', f"Cast: {m['actors']}" if m.get('actors') else '']
        desc = ''.join([f'<img src="{escape(m["img"])}" width="190"/><br/>' if m.get('img') else '',
                        escape(' | '.join(b for b in bits if b)), '<br/><br/>', escape(m.get('description') or ''),
                        f'<br/><a href="{escape(m["trailer"])}">Trailer</a>' if m.get('trailer') else ''])
        link = m.get('imdb_url') or f"https://vuniper.com/?id={m['uid']}"
        out += ['<item>', f'<title>{escape(title)}</title>', f'<link>{escape(link)}</link>',
                f'<guid isPermaLink="false">vuniper-{section}-{m["uid"]}</guid>',
                f'<description><![CDATA[{desc}]]></description>']
        d = rfc822(item_date(m, section))
        if d: out.append(f'<pubDate>{d}</pubDate>')
        for g in (m.get('genres') or '').split(','):
            if g: out.append(f'<category>{escape(g)}</category>')
        out.append('</item>')
    out.append('</channel></rss>')
    return '\n'.join(out)

def stevenlu(items):
    return [{'title': m['title'], 'imdb_id': m['imdb_id'], 'poster_url': m.get('img') or ''} for m in items if m.get('imdb_id')]

args = sys.argv[1:]
out_dir = os.path.dirname(os.path.abspath(__file__))
if '--out' in args:
    i = args.index('--out'); out_dir = args[i + 1]; del args[i:i + 2]
os.makedirs(out_dir, exist_ok=True)
for s in args or ['web']:
    if s not in SECTIONS: raise SystemExit(f'unknown section {s}; pick from {SECTIONS}')
    items = fetch(s)
    open(os.path.join(out_dir, f'vuniper-{s}.xml'), 'w', encoding='utf-8').write(rss(s, items))
    json.dump(stevenlu(items), open(os.path.join(out_dir, f'vuniper-{s}.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'{s}: {len(items)} movies -> vuniper-{s}.xml / .json in {out_dir}')
