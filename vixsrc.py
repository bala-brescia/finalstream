import re
import json
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

ua = UserAgent()

def sanitize_json(js_str):
    """Converte un oggetto JavaScript-like in JSON valido"""
    js_str = re.sub(r',\s*([}\]])', r'\1', js_str)
    js_str = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*):', r'\1"\2"\3:', js_str)
    js_str = re.sub(r"\'([^']*)\'", r'"\1"', js_str)

    return js_str


def extract_js_object(script_text, var_name):
    """Estrae oggetto JS con gestione bilanciamento graffe"""
    try:
        start = script_text.find(f'{var_name} =')
        if start == -1:
            return None

        start_obj = script_text.find('{', start)
        if start_obj == -1:
            return None

        brace_count = 0
        end_obj = start_obj
        for i in range(start_obj, len(script_text)):
            if script_text[i] == '{':
                brace_count += 1
            elif script_text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_obj = i
                    break
        else:
            return None

        json_str = script_text[start_obj:end_obj + 1]
        json_str = sanitize_json(json_str)

        with open('last_clean_json.txt', 'w') as f:
            f.write(json_str)

        return json.loads(json_str)

    except Exception as e:
        print(f"Errore critico in extract_js_object: {str(e)}")
        return None
    
def extract_js_array(script_text, var_name):
    try:
        start = script_text.find(f'{var_name} =')
        if start == -1:
            return None

        start_arr = script_text.find('[', start)
        if start_arr == -1:
            return None

        bracket_count = 0
        end_arr = start_arr
        for i in range(start_arr, len(script_text)):
            if script_text[i] == '[':
                bracket_count += 1
            elif script_text[i] == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    end_arr = i
                    break
        else:
            return None 

        json_str = script_text[start_arr:end_arr + 1]
        json_str = sanitize_json(json_str)

        with open('last_clean_json.txt', 'w') as f:
            f.write(json_str)

        return json.loads(json_str)

    except Exception as e:
        print(f"Errore critico in extract_js_array: {str(e)}")
        return None


def get_vixsrc_stream(tmdb_id, media_type, season=1, episode=1):
    try:
        headers = {
            'User-Agent': ua.random,
            'Referer': 'https://vixsrc.to/',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8',
            'DNT': '1'
        }

        base_url = f"https://vixsrc.to/{'movie' if media_type == 'movie' else 'tv'}/{tmdb_id}"
        if media_type == 'tv':
            base_url += f"/season/{season}/episode/{episode}"

        session = requests.Session()
        response = session.get(base_url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        scripts = soup.find_all('script', string=re.compile('window\.'))
        script_text = '\n'.join(script.string for script in scripts if script.string)

        master_data = extract_js_object(script_text, 'window.masterPlaylist')
        streams_data = extract_js_array(script_text, 'window.streams')
        video_data = extract_js_object(script_text, 'window.video')

        essential_data = {
            'master_playlist': master_data,
            'streams': streams_data,
            'video_info': video_data
        }

        if not all(essential_data.values()):
            missing = [k for k, v in essential_data.items() if not v]
            raise ValueError(f"Dati essenziali mancanti: {missing}")

        token = master_data['params']['token']
        expires = master_data['params']['expires']
        
        processed_streams = []
        
        for stream in streams_data:
            if stream.get('active'):
                clean_url = stream['url'].replace('\\/', '/')
                separator = '&' if '?' in clean_url else '?'
                processed_streams.append({
                    'name': stream.get('name', 'Server'),
                    'url': f"{clean_url}{separator}token={token}&expires={expires}",
                    'quality': video_data.get('quality', 'HD')
                })
        if not processed_streams:
            raise ValueError("Nessuno stream attivo disponibile")
        return {
            'primary_url': processed_streams[0]['url'],
            'backup_urls': [s['url'] for s in processed_streams[1:]],
            'token': token,
            'expires': expires,
            'meta': {
                'title': video_data.get('name'),
                'duration': video_data.get('duration'),
                'quality': video_data.get('quality')
            }
        }

    except requests.RequestException as e:
        print(f"Errore di rete: {type(e).__name__}: {str(e)}")
    except json.JSONDecodeError as e:
        print(f"Errore JSON: {str(e)} - Verifica last_clean_json.txt")
    except Exception as e:
        print(f"Errore imprevisto: {type(e).__name__}: {str(e)}")
    
    return None