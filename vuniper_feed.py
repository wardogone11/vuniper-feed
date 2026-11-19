"""Movie feeds -> RSS + Radarr list, from TMDB. Usage: python vuniper_feed.py [section ...] [--out DIR]
Sections: web bluray theaters upcoming popular anime top100 (default: web)
Writes vuniper-<section>.xml (RSS 2.0) and vuniper-<section>.json (StevenLu format for Radarr).
File names stay the same as the old Vuniper version so existing feed links keep working.
Needs a free TMDB "API Read Access Token" in the TMDB_TOKEN environment variable.
This product uses the TMDB API but is not endorsed or certified by TMDB."""
import json, os, sys, urllib.request, urllib.parse, email.utils, datetime
from xml.sax.saxutils import escape

API = 'https://api.themoviedb.org/3'
IMG = 'https://image.tmdb.org/t/p/w342'
REGION = os.environ.get('TMDB_REGION', 'US')
NAMES = {'web': 'New on digital', 'bluray': 'New on Blu-ray', 'theaters': 'In theaters', 'upcoming': 'Upcoming',
         'popular': 'Popular', 'anime': 'Anime', 'top100': 'Top 100'}
TODAY = datetime.date.today()

def get(path, **params):
    token = os.environ.get('TMDB_TOKEN')
    if not token: raise SystemExit('TMDB_TOKEN is not set (add it as a repository secret)')
    url = f'{API}{path}?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

def listing(section):
    since = (TODAY - datetime.timedelta(days=45)).isoformat()
    if section in ('web', 'bluray'):  # TMDB release type 4 = digital, 5 = physical
        return get('/discover/movie', region=REGION, with_release_type=4 if section == 'web' else 5,
                   **{'release_date.gte': since, 'release_date.lte': TODAY.isoformat()},
                   sort_by='popularity.desc', include_adult='false', **{'vote_count.gte': 5})['results'][:20]
    if section == 'anime':
        return get('/discover/movie', with_genres=16, with_original_language='ja', sort_by='popularity.desc',
                   **{'primary_release_date.gte': (TODAY - datetime.timedelta(days=365)).isoformat()})['results'][:20]
    if section == 'top100':
        return [m for p in range(1, 6) for m in get('/movie/top_rated', region=REGION, page=p)['results']][:100]
    path = {'theaters': '/movie/now_playing', 'upcoming': '/movie/upcoming', 'popular': '/movie/popular'}[section]
    return get(path, region=REGION)['results'][:20]

def details(m):
    return get(f"/movie/{m['id']}", append_to_response='external_ids,release_dates,credits,videos')

def section_date(d, section):
    want = {'web': 4, 'bluray': 5}.get(section)
    if want:
        for r in d.get('release_dates', {}).get('results', []):
            if r['iso_3166_1'] == REGION:
                dates = sorted(x['release_date'][:10] for x in r['release_dates'] if x['type'] == want)
                if dates: return dates[0]
    return d.get('release_date')

def rfc822(s):
    if not s: return None
    dt = datetime.datetime.fromisoformat(s[:10]).replace(tzinfo=datetime.timezone.utc)
    return email.utils.format_datetime(dt)

def rss(section, movies):
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>',
           f'<title>Movies - {escape(NAMES[section])}</title>', '<link>https://www.themoviedb.org/movie</link>',
           f'<description>Movies: {escape(NAMES[section])} (data from TMDB)</description>',
           f'<lastBuildDate>{email.utils.format_datetime(datetime.datetime.now(datetime.timezone.utc))}</lastBuildDate>']
    for d in movies:
        year = (d.get('release_date') or '?')[:4]
        genres = ', '.join(g['name'] for g in d.get('genres', []))
        crew = d.get('credits', {})
        director = ', '.join(c['name'] for c in crew.get('crew', []) if c.get('job') == 'Director')
        cast = ', '.join(c['name'] for c in crew.get('cast', [])[:4])
        rt = d.get('runtime') or 0
        trailer = next((v for v in d.get('videos', {}).get('results', []) if v.get('site') == 'YouTube' and v.get('type') == 'Trailer'), None)
        bits = [f"Score {d['vote_average']:.1f} ({d.get('vote_count', 0)} votes)" if d.get('vote_count') else '', genres,
                f'{rt // 60}h {rt % 60}m' if rt else '', f'Director: {director}' if director else '', f'Cast: {cast}' if cast else '']
        desc = ''.join([f'<img src="{IMG}{escape(d["poster_path"])}" width="190"/><br/>' if d.get('poster_path') else '',
                        escape(' | '.join(b for b in bits if b)), '<br/><br/>', escape(d.get('overview') or ''),
                        f'<br/><a href="https://www.youtube.com/watch?v={escape(trailer["key"])}">Trailer</a>' if trailer else ''])
        imdb = d.get('external_ids', {}).get('imdb_id') or d.get('imdb_id')
        link = f'https://www.imdb.com/title/{imdb}/' if imdb else f"https://www.themoviedb.org/movie/{d['id']}"
        out += ['<item>', f"<title>{escape(d['title'])} ({year})</title>", f'<link>{escape(link)}</link>',
                f'<guid isPermaLink="false">tmdb-{section}-{d["id"]}</guid>', f'<description><![CDATA[{desc}]]></description>']
        p = rfc822(section_date(d, section))
        if p: out.append(f'<pubDate>{p}</pubDate>')
        out += [f'<category>{escape(g["name"])}</category>' for g in d.get('genres', [])]
        out.append('</item>')
    out.append('</channel></rss>')
    return '\n'.join(out)

def stevenlu(movies):
    return [{'title': d['title'], 'imdb_id': d['external_ids']['imdb_id'],
             'poster_url': f"{IMG}{d['poster_path']}" if d.get('poster_path') else ''}
            for d in movies if d.get('external_ids', {}).get('imdb_id')]

if __name__ == '__main__':
    args = sys.argv[1:]
    out_dir = os.path.dirname(os.path.abspath(__file__))
    if '--out' in args:
        i = args.index('--out'); out_dir = args[i + 1]; del args[i:i + 2]
    os.makedirs(out_dir, exist_ok=True)
    for s in args or ['web']:
        if s not in NAMES: raise SystemExit(f'unknown section {s}; pick from {tuple(NAMES)}')
        movies = [details(m) for m in listing(s)]
        open(os.path.join(out_dir, f'vuniper-{s}.xml'), 'w', encoding='utf-8').write(rss(s, movies))
        json.dump(stevenlu(movies), open(os.path.join(out_dir, f'vuniper-{s}.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        print(f'{s}: {len(movies)} movies -> vuniper-{s}.xml / .json in {out_dir}')
