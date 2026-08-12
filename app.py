def fetch_sencrop():
    login_url = "https://api.sencrop.com/v1/auth/login"
    payload = {"email": "marika.d@drusian.it", "password": "marika.drusian"}

    try:
        session = requests.Session()
        res_login = session.post(login_url, json=payload, headers=HEADERS, timeout=8)

        if res_login.status_code == 200:
            token_data = res_login.json()
            token = token_data.get("token") or token_data.get("accessToken") or token_data.get("jwt")
            
            auth_headers = {
                **HEADERS,
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            }
            
            debug_info = "Login OK."
            
            # Proviamo diversi endpoint possibili per recuperare l'ID della stazione
            endpoints = [
                "https://api.sencrop.com/v1/devices", 
                "https://api.sencrop.com/v2/devices",
                "https://api.sencrop.com/v1/stations"
            ]
            
            for endpoint in endpoints:
                res_dev = session.get(endpoint, headers=auth_headers, timeout=8)
                debug_info += f" [{endpoint[-7:]}:{res_dev.status_code}]"
                
                if res_dev.status_code == 200:
                    devices = res_dev.json()
                    
                    # Estrae la lista ovunque Sencrop l'abbia nascosta
                    if isinstance(devices, dict) and "data" in devices:
                        devices = devices["data"]
                    elif isinstance(devices, dict) and "devices" in devices:
                        devices = devices["devices"]
                        
                    if isinstance(devices, list):
                        if len(devices) > 0:
                            dev_id = devices[0].get("id")
                            debug_info += f" ID:{dev_id}."
                            
                            # Cerca i dati più recenti
                            data_urls = [
                                f"https://api.sencrop.com/v1/devices/{dev_id}/data/latest",
                                f"https://api.sencrop.com/v2/devices/{dev_id}/data/latest"
                            ]
                            
                            for url_data in data_urls:
                                res_data = session.get(url_data, headers=auth_headers, timeout=8)
                                if res_data.status_code == 200:
                                    m = res_data.json()
                                    if "data" in m: m = m["data"]
                                    
                                    t = m.get('temperature') or m.get('temp') or m.get('airTemperature')
                                    h = m.get('humidity') or m.get('relativeHumidity') or m.get('hum')
                                    w = m.get('windSpeed') or m.get('wind_speed') or m.get('wind')
                                    r = m.get('rain') or m.get('rainfall') or m.get('cumulatedRain') or 0.0

                                    return {
                                        "name": "Sencrop CART (Drusian)",
                                        "url": "https://app.sencrop.com/",
                                        "status": "online",
                                        "temp": f"{t} °C" if t is not None else "N/D",
                                        "humidity": f"{h} %" if h is not None else "N/D",
                                        "pressure": f"Pioggia: {r} mm",
                                        "wind": f"{w} km/h" if w is not None else "N/D",
                                        "updated": datetime.now(ROME_TZ).strftime("%H:%M:%S")
                                    }
                            debug_info += " Dati vuoti."
                        else:
                            debug_info += " Lista vuota."
                    else:
                        debug_info += " No list."

            # Se arriva qui, non ha trovato i dati: mostra il debug sulla dashboard
            return {
                "name": "Sencrop Debug",
                "url": "https://app.sencrop.com/",
                "status": "offline",
                "temp": "Debug:",
                "humidity": "Info:",
                "pressure": debug_info,
                "wind": "N/D",
                "updated": datetime.now(ROME_TZ).strftime("%H:%M:%S")
            }
        else:
            return {
                "name": "Sencrop Error",
                "url": "https://app.sencrop.com/",
                "status": "offline",
                "temp": "Errore",
                "humidity": f"Code: {res_login.status_code}",
                "pressure": "Credenziali errate?",
                "wind": "N/D",
                "updated": datetime.now(ROME_TZ).strftime("%H:%M:%S")
            }
    except Exception as e:
        print(f"Errore Sencrop: {e}")
        return {
            "name": "Sencrop Exception",
            "url": "https://app.sencrop.com/",
            "status": "offline",
            "temp": "N/D",
            "humidity": "N/D",
            "pressure": str(e)[:30],
            "wind": "N/D",
            "updated": "Errore"
        }
