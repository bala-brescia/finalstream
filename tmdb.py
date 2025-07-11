import requests
import os
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv('TMDB_API_KEY')
BASE_URL = "https://api.themoviedb.org/3"

def search_tmdb(query):
    try:
        url = f"{BASE_URL}/search/multi?api_key={TMDB_API_KEY}&query={query}&language=it-IT"
        response = requests.get(url)
        response.raise_for_status()
        
        return [{
            'id': item['id'],
            'title': item.get('title') or item.get('name'),
            'type': 'movie' if item['media_type'] == 'movie' else 'tv',
            'year': (item.get('release_date') or item.get('first_air_date'))[:4] if item.get('release_date') or item.get('first_air_date') else 'N/A',
            'poster': f"https://image.tmdb.org/t/p/w300{item['poster_path']}" if item.get('poster_path') else None,
            'overview': item.get('overview', 'Nessuna descrizione disponibile')
        } for item in response.json()['results'] if item['media_type'] in ['movie', 'tv']]
    
    except Exception as e:
        print(f"Errore ricerca TMDB: {str(e)}")
        return []

def get_tmdb_details(tmdb_id, media_type):
    try:
        endpoint = 'movie' if media_type == 'movie' else 'tv'
        url = f"{BASE_URL}/{endpoint}/{tmdb_id}?api_key={TMDB_API_KEY}&language=it-IT&append_to_response=videos"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Errore dettagli TMDB: {str(e)}")
        return None
    
def get_tmdb_popular_movies():
    try:
        url = f"{BASE_URL}/movie/popular?api_key={TMDB_API_KEY}&language=it-IT&page=1"
        response = requests.get(url)
        response.raise_for_status()
        results = response.json().get("results", [])
        return [{
            'id': movie['id'],
            'title': movie['title'],
            'release_date': movie.get('release_date', '')[:4],
            'poster_path': movie['poster_path'],
            'vote_average': movie.get('vote_average', 0)
        } for movie in results]
    except Exception as e:
        print(f"Errore nel recupero dei film popolari: {e}")
        return []
    
def get_tmdb_popular_tvshows():
    try:
        url = f"{BASE_URL}/tv/popular?api_key={TMDB_API_KEY}&language=it-IT&page=1"
        response = requests.get(url)
        response.raise_for_status()
        results = response.json().get("results", [])
        return [{
            'id': show['id'],
            'name': show['name'],
            'first_air_date': show.get('first_air_date', '')[:4],
            'poster_path': show['poster_path'],
            'vote_average': show.get('vote_average', 0)
        } for show in results]
    except Exception as e:
        print(f"Errore nel recupero delle serie TV popolari: {e}")
        return []

def unified_tmdb_search(query):
    results = []

    try:
        url = f"{BASE_URL}/search/multi?api_key={TMDB_API_KEY}&language=it-IT&query={query}"
        response = requests.get(url)
        response.raise_for_status()
        items = response.json().get("results", [])

        for item in items:
            media_type = item.get("media_type")
            if media_type not in ["movie", "tv"]:
                continue 

            results.append({
                'id': item['id'],
                'title': item.get('title') or item.get('name'),
                'year': (item.get('release_date') or item.get('first_air_date') or '')[:4],
                'poster_path': item['poster_path'],
                'vote_average': item.get('vote_average', 0),
                'type': media_type
            })

    except Exception as e:
        print(f"Errore nella ricerca unificata: {e}")

    return results


