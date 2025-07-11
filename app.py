from flask import Flask, render_template, request, Response, redirect, jsonify, session, url_for
import requests
import json
import re
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import traceback
import httpx
from urllib.parse import urlparse, parse_qs, unquote, urlencode, quote
import base64
from tmdb import get_tmdb_popular_movies,get_tmdb_popular_tvshows, unified_tmdb_search
from dotenv import load_dotenv
import os


load_dotenv()

TMDB_API_KEY = os.getenv('TMDB_API_KEY')

ua = UserAgent()

app = Flask(__name__)

app.secret_key = os.getenv('FLASK_SECRET_KEY')
GLOBAL_PASSWORD = os.getenv('SITE_PASSWORD')

@app.before_request
def check_password():
    allowed_routes = ['login', 'static']  # static per file css/js
    if request.endpoint not in allowed_routes and not session.get('logged_in'):
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == GLOBAL_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Password errata")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route('/stream')
def stream():
    try:
        # Decodifica e verifica l'URL
        url = unquote(request.args.get('url', ''))
        if not url:
            return {'error': 'URL mancante'}, 400

        # Verifica i domini consentiti
        allowed_hosts = ['vixcloud.co', 'vixsrc.to']
        host = urlparse(url).netloc
        if not any(allowed in host for allowed in allowed_hosts):
            return {'error': 'Dominio non consentito'}, 403

        # Configura gli header per evitare blocchi
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://vixcloud.co/',
            'Origin': 'https://vixcloud.co'
        }

        # Effettua la richiesta al server remoto
        remote_response = requests.get(url, headers=headers, stream=True, timeout=10)

        # Restituisci il contenuto come stream
        return Response(
            remote_response.iter_content(chunk_size=8192),
            content_type=remote_response.headers.get('Content-Type', 'application/vnd.apple.mpegurl'),
            headers={
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'no-cache'
            }
        )

    except requests.exceptions.RequestException as e:
        return {'error': f'Errore di connessione: {str(e)}'}, 502
    except Exception as e:
        return {'error': f'Errore del server: {str(e)}'}, 500

@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    headers = {'Referer': 'https://vixcloud.co', 'Origin': 'https://vixcloud.co'}
    resp = requests.get(url, headers=headers, stream=True)
    return Response(resp.iter_content(chunk_size=1024), content_type=resp.headers['Content-Type'])


@app.route('/proxy_stream')
def proxy_stream():
    url = request.args.get('url')
    if not url:
        return 'Missing URL', 400
    try:
        r = requests.get(url, stream=True, timeout=10)
        r.raise_for_status()

        def generate():
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        content_type = r.headers.get('Content-Type', 'application/vnd.apple.mpegurl')
        headers = {
            'Content-Type': content_type,
            'Access-Control-Allow-Origin': '*'
        }
        return Response(generate(), headers=headers)
    except Exception as e:
        return f'Errore proxy: {str(e)}', 500
    

def extract_vixsrc_data(script_content):
    """Estrae tutti i dati dallo script VixSrc con regex perfezionata"""
    try:
        script_content = script_content.replace('\n', ' ')
        
        video_match = re.search(r'window\.video\s*=\s*({.*?})(?=;\s*window\.streams)', script_content)
        if not video_match:
            raise ValueError("video_data non trovato")
        video_data = json.loads(video_match.group(1))
        
        streams_match = re.search(r'window\.streams\s*=\s*(\[.*?\])(?=;\s*window\.masterPlaylist)', script_content)
        if not streams_match:
            raise ValueError("streams_data non trovato")
        streams_data = json.loads(streams_match.group(1))
        
        master_match = re.search(
            r'window\.masterPlaylist\s*=\s*({.*?})\s*window\.', 
            script_content,
            re.DOTALL
        )
        
        if not master_match:
            raise ValueError("masterPlaylist non trovato")
            
        master_str = master_match.group(1)
        master_str = master_str.replace("'", '"')
        master_str = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)\s*:', r'\1"\2":', master_str)
        master_str = re.sub(r':\s*([a-zA-Z0-9_]+)(\s*[,}])', r': "\1"\2', master_str)
        master_str = re.sub(r',\s*([}\]])', r'\1', master_str)
        
        try:
            master_data = json.loads(master_str)
            return video_data, streams_data, master_data
        except json.JSONDecodeError as e:
            raise ValueError(f"Errore decodifica masterPlaylist: {str(e)}")

    except Exception as e:
        raise


def get_vixsrc_stream(tmdb_id, media_type, season=1, episode=1):
    try:
        BASE_URL = "https://vixsrc.to"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Referer': f'{BASE_URL}/',
            'Origin': BASE_URL
        }
        if media_type == 'movie':
            embed_url = f"{BASE_URL}/movie/{tmdb_id}"
        else:
            embed_url = f"{BASE_URL}/tv/{tmdb_id}/{season}/{episode}"

        session = requests.Session()
        response = session.get(embed_url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        script_tag = soup.find('script', string=re.compile(r'window\.(video|streams|masterPlaylist)'))
        if not script_tag or not script_tag.string:
            raise ValueError("Script con dati del player non trovato")

        with open('last_script.js', 'w', encoding='utf-8') as f:
            f.write(script_tag.string)
        video_data, streams_data, master_data = extract_vixsrc_data(script_tag.string)
        
        required_master_fields = ['params', 'url']
        if not all(field in master_data for field in required_master_fields):
            raise ValueError("Struttura masterPlaylist incompleta")
        
        active_stream = next(
            (s for s in streams_data if s.get('active') in [1, True] and 'url' in s),
            None
        )
        if not active_stream:
            raise ValueError("Nessuno stream attivo disponibile")

        base_url = active_stream['url'].replace('\\/', '/')
        parsed = urlparse(base_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        param = parse_qs(parsed.query)
        param_str = parsed.query

        token = master_data['params'].get('token')
        expires = master_data['params'].get('expires')

        raw_params = f"{param_str}&h=1&token={token}&expires={expires}"
        encoded_params = quote(raw_params)

        if not all([base_url, token, expires]):
            raise ValueError("Parametri mancanti per generare l'URL")

        final_url = f"{base_url}?{encoded_params}"

        return {
            'playlist_url': final_url,
            'meta': {
                'title': video_data.get('name'),
                'quality': video_data.get('quality', 'HD'),
                'source': 'VixSrc',
                'expires_at': expires 
            }
        }

    except Exception as e:
        return None

def get_tmdb_data(tmdb_id,type):
    url = f"https://api.themoviedb.org/3/{type}/{tmdb_id}?api_key={TMDB_API_KEY}&language=it-IT"
    resp = requests.get(url)
    if resp.status_code == 200:
        return resp.json()
    return None

@app.route('/player')
def player():
    tmdb_id = request.args.get('id')
    media_type = request.args.get('type','movie')

    if not tmdb_id:
        print("ID TMDB mancante")
        return "ID TMDB mancante", 400

    movie_data = get_tmdb_data(tmdb_id,media_type)

    if not movie_data:
        return "Film non trovato", 404

    stream_info = get_vixsrc_stream(tmdb_id, media_type)
    if not stream_info:
        return "Stream non disponibile", 503

    playlist_url = stream_info['playlist_url']

    return render_template('player.html', movie=movie_data, embed_url=playlist_url, type=media_type)

@app.route('/')
def index():
    query = request.args.get("q")
    if query:
        results = unified_tmdb_search(query)
        return render_template('index.html', results=results, query=query)
    else:
        movies = get_tmdb_popular_movies()
        tvshows = get_tmdb_popular_tvshows()
        return render_template('index.html', movies=movies, tvshows=tvshows)

@app.route('/api/tv/<int:tmdb_id>/season/<int:season_number>')
def season_info(tmdb_id, season_number):
    season_data = get_season(tmdb_id, season_number)
    if season_data:
        return jsonify(season_data)
    return jsonify({'error': 'Stagione non trovata'}), 404


def get_season(tmdb_id,season_number):
    url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{season_number}?api_key={TMDB_API_KEY}&language=it-IT"
    resp = requests.get(url)
    if resp.status_code == 200:
        return resp.json()
    return None

@app.route('/api/stream_url')
def get_stream_url():
    tmdb_id = request.args.get('tmdb_id')
    season = request.args.get('season', type=int)
    episode = request.args.get('episode', type=int)

    if not tmdb_id or not season or not episode:
        return jsonify({'error': 'Parametri mancanti'}), 400

    stream = get_vixsrc_stream(tmdb_id, 'tv', season=season, episode=episode)
    if not stream:
        return jsonify({'error': 'Stream non disponibile'}), 503

    return jsonify({'url': stream['playlist_url']})


if __name__ == '__main__':
    app.run(debug=True)


