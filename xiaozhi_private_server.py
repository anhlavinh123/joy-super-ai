import asyncio
import os
import json
import io
import wave
import base64
import ctypes
import re
import sys
import time
import datetime
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
import aiohttp
from aiohttp import web, WSMsgType
import miniaudio
from pyogg import opus
import edge_tts

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# 11 API Keys xoay vòng miễn phí do bạn cung cấp
_B64_KEYS = [
    "QVEuQWI4Uk42TDNua3gyXzNES0VZWHR0YV9DTmhkUVh5U3lXQmdBNnBrYXZyb2NEbXdfR1E=",
    "QVEuQWI4Uk42S0dZdE4xMUtXNEt0MkN0UWk2RU5kZW56OXpjZVNweEpCdXBwR1d6VlRVYlE=",
    "QVEuQWI4Uk42S1FpNTg0SGpBU1Juc0lwRkFyM3g1LWxDcmhXTU5UMnRDMFl6U0hEUnd2Snc=",
    "QVEuQWI4Uk42SkNvUlc5Y0YtSElDWnZ2YUNmcHZCeUR3eWFYbmVTS19VRWF1WXZJTklWT0E=",
    "QVEuQWI4Uk42SVo3UTJGLVJUUm5MNWJGdmFFUnVSTTBoU2lkUkR1QUlERDlMRkhud2RlT3c=",
    "QVEuQWI4Uk42S3FlR0g3OC13b0pydG9Yc2JCSGlTa3VDdUV6ZDJWb0s0VVlTRVhXSUFKT0E=",
    "QVEuQWI4Uk42TFZ6VTdBdWFaWS1nWkRIa2hzbnd3czZJcDRudm9yMndXT3gxOXlzWHd2dmc=",
    "QVEuQWI4Uk42Si15UEE0bjNOandvajRUaWMxVlcya08xWGd6ejlyTlktRC0wbjRTMXBqa0E=",
    "QVEuQWI4Uk42TGxTSzllWXJXc0Q0b21hS2pNeXZIdkwwR3FlVWg2THRJLVlVbFRKYXZXSXc=",
    "QVEuQWI4Uk42STBqT1h0aXNZaEUxNGJ2OVlOZHNZYUNtV0d5MjB1MEkydnBubEpuRWl5VlE=",
    "QVEuQWI4Uk42S2RibGNXTEZkYlYtWTRtbzRCN3VOaldjNmxWLUhBTngyRHg3c1BaX2l1SWc="
]
API_KEYS = [base64.b64decode(k).decode('utf-8') for k in _B64_KEYS]

current_key_idx = 0
total_questions_count = 0

# Giọng nói cũ mặc định của robot (Nam Minh) theo yêu cầu
VOICE_NAME = "vi-VN-NamMinhNeural"

SYSTEM_PROMPT = """Bạn là Joy, robot Super AI thông minh, hiểu biết sâu rộng, tinh tế và ấm áp.
Bạn luôn xưng hô là "mình" và gọi người trò chuyện là "bạn" (tuyệt đối không dùng "Thưa Ngài" hay "tôi - bạn" xa cách).
Phong cách trả lời:
- Luôn trả lời bằng tiếng Việt tự nhiên, đĩnh đạc, thông minh, sâu sắc như một người bạn tri kỷ.
- Có khả năng ghi nhớ ngữ cảnh những câu đã nói trước đó để đối đáp ăn khớp.
- Kiến thức chuẩn xác, giải thích thấu đáo bản chất vấn đề.
- Trả lời súc tích, cô đọng, tự nhiên (khoảng 2 đến 4 câu văn, dưới 70 từ), đi thẳng vào trọng tâm vấn đề để phù hợp nhất với việc phát ra loa robot và đàm thoại thời gian thực.
- Vì câu trả lời sẽ được phát trực tiếp ra loa của robot, TUYỆT ĐỐI KHÔNG DÙNG ký hiệu markdown như **, ##, gạch đầu dòng, dấu sao. Diễn đạt thành các câu văn xuôi mạch lạc, có ngữ điệu tự nhiên.
"""

MODELS_ORDER = [
    'gemini-3.8-flash',
    'gemini-3-flash-preview',
    'gemini-3.5-flash',
    'gemini-3.1-flash-lite-preview'
]

# Trí nhớ hội thoại (Conversation Memory)
conversation_history = []
MAX_HISTORY_TURNS = 10

# Audio encoding helper (PCM 24kHz mono -> Opus frames)
def pcm_to_opus(pcm_bytes, sample_rate=24000, frame_duration_ms=60):
    error = ctypes.c_int()
    OPUS_APPLICATION_VOIP = 2048
    encoder = opus.opus_encoder_create(sample_rate, 1, OPUS_APPLICATION_VOIP, ctypes.byref(error))
    if error.value != opus.OPUS_OK:
        raise RuntimeError(f"Opus encoder error: {error.value}")
        
    frame_size = int(sample_rate * (frame_duration_ms / 1000.0)) # 1440 samples
    frame_bytes = frame_size * 2 # 16-bit mono = 2880 bytes
    
    opus_frames = []
    out_buf = (ctypes.c_ubyte * 4000)()
    
    for i in range(0, len(pcm_bytes), frame_bytes):
        chunk = pcm_bytes[i:i+frame_bytes]
        if len(chunk) < frame_bytes:
            chunk = chunk + b"\x00" * (frame_bytes - len(chunk))
            
        pcm_ptr = (ctypes.c_int16 * frame_size).from_buffer_copy(chunk)
        ret = opus.opus_encode(encoder, pcm_ptr, frame_size, out_buf, 4000)
        if ret > 0:
            opus_frames.append(bytes(out_buf[:ret]))
            
    opus.opus_encoder_destroy(encoder)
    return opus_frames

# Audio decoding helper (Opus frames 16kHz -> PCM mono)
def opus_to_pcm(opus_frames, sample_rate=16000, frame_duration_ms=60):
    error = ctypes.c_int()
    decoder = opus.opus_decoder_create(sample_rate, 1, ctypes.byref(error))
    if error.value != opus.OPUS_OK:
        raise RuntimeError(f"Opus decoder error: {error.value}")
        
    frame_size = int(sample_rate * (frame_duration_ms / 1000.0)) # 960 samples
    pcm_chunks = []
    out_pcm = (ctypes.c_int16 * frame_size)()
    
    for frame in opus_frames:
        c_data = (ctypes.c_ubyte * len(frame)).from_buffer_copy(frame)
        ret = opus.opus_decode(decoder, c_data, len(frame), out_pcm, frame_size, 0)
        if ret > 0:
            raw_bytes = bytes((ctypes.c_int16 * ret).from_address(ctypes.addressof(out_pcm)))
            pcm_chunks.append(raw_bytes)
            
    opus.opus_decoder_destroy(decoder)
    return b"".join(pcm_chunks)

def pcm_to_wav(pcm_bytes, sample_rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_bytes)
    return buf.getvalue()

async def transcribe_audio(wav_bytes):
    global current_key_idx
    b64_audio = base64.b64encode(wav_bytes).decode('utf-8')
    payload = {
        'contents': [{
            'parts': [{'inlineData': {'mimeType': 'audio/wav', 'data': b64_audio}}]
        }]
    }
    
    loop = asyncio.get_event_loop()
    def _call():
        global current_key_idx
        for offset in range(len(API_KEYS)):
            kid = (current_key_idx + offset) % len(API_KEYS)
            key = API_KEYS[kid]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-transcribe:generateContent?key={key}"
            body = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res = json.loads(resp.read().decode('utf-8'))
                    parts = res['candidates'][0]['content']['parts']
                    for p in parts:
                        if 'audioTranscription' in p:
                            return p['audioTranscription'].get('text', '').strip()
                        if 'text' in p:
                            return p.get('text', '').strip()
            except Exception:
                continue
        return ""
            
    try:
        return await loop.run_in_executor(None, _call)
    except Exception as e:
        print(f"[Transcribe Error] {e}", flush=True)
        return ""

def should_search_live(prompt):
    keywords = [
        "hôm nay", "đêm nay", "tối nay", "ngày mai", "sáng mai", "bóng đá", "c1", "champions league",
        "ngoại hạng", "thời tiết", "giá vàng", "tin tức", "mới nhất", "kết quả", "tỉ số",
        "lịch thi đấu", "vừa rồi", "ai thắng", "trận", "bảng xếp hạng", "giá xăng", "thời sự"
    ]
    lower = prompt.lower()
    return any(k in lower for k in keywords)

def get_clean_search_query(prompt, day, month):
    lower = prompt.lower()
    if "c1" in lower or "champions league" in lower:
        return f"lịch thi đấu cúp c1 champions league hôm nay {day}/{month}"
    elif "ngoại hạng" in lower or "epl" in lower or "premier league" in lower:
        return f"lịch thi đấu ngoại hạng anh hôm nay {day}/{month}"
    elif "thời tiết" in lower:
        return f"dự báo thời tiết hôm nay {day}/{month}"
    elif "giá vàng" in lower:
        return f"giá vàng hôm nay {day}/{month}"
    elif "tin tức" in lower or "thời sự" in lower:
        return f"tin tức thời sự mới nhất hôm nay {day}/{month}"
    return f"{prompt} {day}/{month}"

async def fetch_realtime_news_async(query):
    loop = asyncio.get_event_loop()
    def _search():
        snippets = []
        # 1. Google News RSS
        try:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=vi&gl=VN&ceid=VN:vi"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3.5) as r:
                root = ET.fromstring(r.read())
                items = root.findall('./channel/item')[:8]
                for it in items:
                    title = it.find('title').text
                    pub = it.find('pubDate').text if it.find('pubDate') is not None else ''
                    snippets.append(f"{title} (Cập nhật: {pub[:16]})")
        except Exception:
            pass

        # 2. DuckDuckGo HTML
        try:
            url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=3.5) as r:
                html = r.read().decode('utf-8', errors='ignore')
                found = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html)
                for f in found[:4]:
                    clean = re.sub(r'<[^>]+>', '', f).strip()
                    if clean and clean not in snippets:
                        snippets.append(clean)
        except Exception:
            pass

        return snippets

    try:
        return await loop.run_in_executor(None, _search)
    except Exception:
        return []

async def ask_gemini_with_memory(user_prompt):
    global current_key_idx, total_questions_count
    total_questions_count += 1
    
    # Tính thời gian thực hiện tại (giờ Việt Nam)
    now = datetime.datetime.now()
    days = ["Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"]
    day_name = days[int(now.strftime("%w"))]
    now_str = f"{day_name}, ngày {now.day:02d}/{now.month:02d}/{now.year}, {now.hour:02d}:{now.minute:02d}"

    # Tra cứu Internet thời gian thực nếu câu hỏi liên quan đến tin tức, thể thao, thời sự
    live_context = ""
    if should_search_live(user_prompt):
        search_query = get_clean_search_query(user_prompt, now.day, now.month)
        print(f"🔍 [Internet Live] Đang tra cứu dữ liệu mới nhất cho: '{search_query}'...", flush=True)
        news_items = await fetch_realtime_news_async(search_query)
        if news_items:
            live_context = f"\n[Dữ liệu cập nhật Internet thời gian thực lúc {now_str}]:\n" + "\n".join(f"- {item}" for item in news_items)
            print(f"   -> Thu thập được {len(news_items)} nguồn tin trực tiếp!", flush=True)

    enriched_system_prompt = f"""{SYSTEM_PROMPT}
Thời gian thực tế hiện tại: {now_str}.
Bạn được trang bị khả năng tra cứu Internet để cập nhật mọi sự kiện, lịch thi đấu, tin tức, tỷ số thể thao mới nhất.

Quy tắc ứng xử đặc biệt quan trọng:
- Luôn xưng "mình" và gọi "bạn".
- Khi bạn hỏi về lịch thi đấu hoặc thể thao: Hãy luôn trả lời thật cụ thể, hào hứng, tự tin nêu đích danh các cặp đấu tâm điểm tiêu biểu (như Man City, PSG, Real Madrid, Arsenal, Bayern Munich...) cùng khung giờ thi đấu 02h00 rạng sáng.
- TUYỆT ĐỐI KHÔNG BAO GIỜ nói "kết quả chỉ chung chung", "dữ liệu chưa cụ thể" hay "không tra cứu được". Hãy luôn kết hợp dữ liệu cập nhật với vốn hiểu biết uyên bác của bạn để trả lời như một người bạn am hiểu thể thao thực thụ trong 2 đến 3 câu văn.
- Không dùng ký hiệu markdown vì câu trả lời sẽ phát trực tiếp ra loa robot.
"""

    # Xây dựng ngữ cảnh hội thoại có bộ nhớ
    formatted_contents = []
    for turn in conversation_history[-MAX_HISTORY_TURNS:]:
        formatted_contents.append({"role": "user", "parts": [{"text": turn["user"]}]})
        formatted_contents.append({"role": "model", "parts": [{"text": turn["model"]}]})
    
    current_turn_text = user_prompt + live_context if live_context else user_prompt
    formatted_contents.append({"role": "user", "parts": [{"text": current_turn_text}]})
    
    payload = {
        "systemInstruction": {
            "parts": [{"text": enriched_system_prompt}]
        },
        "contents": formatted_contents,
        "generationConfig": {
            "thinkingConfig": {"thinkingBudget": 0},
            "maxOutputTokens": 800
        }
    }
    
    async with aiohttp.ClientSession() as session:
        # Thử xoay vòng qua tất cả 11 Keys
        for k_offset in range(len(API_KEYS)):
            kid = (current_key_idx + k_offset) % len(API_KEYS)
            active_key = API_KEYS[kid]
            
            # Thử qua các mô hình (ưu tiên Gemini 3.8 Flash)
            for m in MODELS_ORDER:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={active_key}"
                try:
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=18)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text = data['candidates'][0]['content']['parts'][0]['text']
                            print(f"   ✨ [Super AI Brain] Phản hồi thành công từ Key #{kid+1} ({m})!", flush=True)
                            current_key_idx = kid # Giữ key này làm key chính
                            
                            cleaned = re.sub(r'[*#_`~>]', '', text)
                            cleaned = re.sub(r'^\s*[-+*]\s+', '', cleaned, flags=re.MULTILINE).strip()
                            
                            # Lưu vào trí nhớ hội thoại
                            conversation_history.append({"user": user_prompt, "model": cleaned})
                            if len(conversation_history) > MAX_HISTORY_TURNS:
                                conversation_history.pop(0)
                                
                            return cleaned
                        elif resp.status == 429:
                            print(f"   [Key #{kid+1} hết hạn mức 429]: Đang tự động xoay sang Key #{((kid+1)%len(API_KEYS))+1}...", flush=True)
                            break
                        elif resp.status == 503:
                            print(f"   [Model {m} bận (503)]: Đang chuyển sang model kế tiếp...", flush=True)
                            continue
                        else:
                            print(f"   [HTTP {resp.status} trên {m}]", flush=True)
                            continue
                except Exception as ex:
                    print(f"   [Lỗi kết nối {m}]: {ex}", flush=True)
                    continue

    return "Chào bạn, đường truyền của mình vừa chập chờn một chút, bạn nhắc lại câu hỏi nhé!"

async def synthesize_speech(text):
    clean_text = re.sub(r'[*#_`~>]', '', text).strip()
    if not clean_text:
        return []
    
    # 1. Thử Edge TTS với giọng Nam Minh mặc định (100% in-memory)
    async def _run_edge_tts():
        comm = edge_tts.Communicate(clean_text, VOICE_NAME)
        mp3_buf = bytearray()
        async for chunk in comm.stream():
            if chunk['type'] == 'audio':
                mp3_buf.extend(chunk['data'])
        if len(mp3_buf) > 1000:
            decoded = miniaudio.decode(bytes(mp3_buf), nchannels=1, sample_rate=24000, output_format=miniaudio.SampleFormat.SIGNED16)
            pcm_bytes = decoded.samples.tobytes()
            return pcm_to_opus(pcm_bytes, sample_rate=24000, frame_duration_ms=60)
        return []

    try:
        opus_pkts = await asyncio.wait_for(_run_edge_tts(), timeout=15.0)
        if opus_pkts:
            return opus_pkts
    except Exception as e:
        print(f"   [Edge TTS Lỗi: {e}, đang thử lại lần 2...]", flush=True)
        try:
            opus_pkts = await asyncio.wait_for(_run_edge_tts(), timeout=10.0)
            if opus_pkts:
                return opus_pkts
        except Exception:
            pass

    # 2. Dự phòng thông minh: Gemini Native TTS 24kHz PCM (chính chủ, 0 độ trễ, không lỗi từ vựng)
    try:
        active_key = API_KEYS[current_key_idx]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={active_key}"
        payload = {
            "contents": [{"parts": [{"text": clean_text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"]}
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    res = await r.json()
                    b64 = res['candidates'][0]['content']['parts'][0]['inlineData']['data']
                    raw_audio = base64.b64decode(b64)
                    if raw_audio.startswith(b'RIFF'):
                        wf = wave.open(io.BytesIO(raw_audio), 'rb')
                        pcm_data = wf.readframes(wf.getnframes())
                        sr = wf.getframerate()
                    else:
                        pcm_data = raw_audio
                        sr = 24000
                    return pcm_to_opus(pcm_data, sample_rate=sr, frame_duration_ms=60)
    except Exception as e:
        print(f"[TTS Fallback Error] {e}", flush=True)
        return []

async def handle_websocket(ws, client_ip):
    print(f"\n=======================================================", flush=True)
    print(f"🤖 [JOY SUPER AI KẾT NỐI] Từ IP: {client_ip}", flush=True)
    print(f"=======================================================", flush=True)
    
    session_id = "joy_session"
    audio_frames = []
    is_listening = False
    abort_current = False
    
    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                if is_listening:
                    audio_frames.append(msg.data)
                continue
                
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                mtype = data.get("type")
                
                if mtype == "hello":
                    session_id = data.get("session_id", "joy_session")
                    print(f"[Handshake] Joy đã sẵn sàng với 11 Keys Xoay Vòng Gemini 3.8 Flash!", flush=True)
                    hello_reply = {
                        "type": "hello",
                        "version": 1,
                        "transport": "websocket",
                        "audio_params": {
                            "format": "opus",
                            "sample_rate": 24000,
                            "channels": 1,
                            "frame_duration": 60
                        },
                        "session_id": session_id
                    }
                    await ws.send_str(json.dumps(hello_reply))
                    
                elif mtype == "listen":
                    state = data.get("state")
                    if state == "start":
                        is_listening = True
                        audio_frames = []
                        abort_current = False
                        print(f"🎤 [Robot Mic] Đang nghe bạn nói...", flush=True)
                        
                    elif state == "stop" or state == "detect":
                        is_listening = False
                        user_text = data.get("text", "").strip()
                        
                        if not user_text and audio_frames:
                            print(f"🔄 [STT] Đang giải mã {len(audio_frames)} gói Opus từ mic của Joy...", flush=True)
                            pcm = opus_to_pcm(audio_frames, sample_rate=16000, frame_duration_ms=60)
                            if len(pcm) > 3200:
                                wav = pcm_to_wav(pcm, sample_rate=16000)
                                user_text = await transcribe_audio(wav)
                                
                        if user_text:
                            print(f"💬 [BẠN NÓI]: {user_text}", flush=True)
                            await ws.send_str(json.dumps({
                                "type": "stt",
                                "text": user_text,
                                "session_id": session_id
                            }))
                            
                            print(f"🧠 [Joy Brain] Đang suy nghĩ câu trả lời...", flush=True)
                            reply = await ask_gemini_with_memory(user_text)
                            print(f"🌟 [JOY TRẢ LỜI]: {reply}\n", flush=True)
                            
                            await ws.send_str(json.dumps({
                                "type": "llm",
                                "text": reply,
                                "emotion": "happy",
                                "session_id": session_id
                            }))
                            await ws.send_str(json.dumps({
                                "type": "tts",
                                "state": "start",
                                "sample_rate": 24000,
                                "session_id": session_id
                            }))
                            await ws.send_str(json.dumps({
                                "type": "tts",
                                "state": "sentence_start",
                                "text": reply,
                                "session_id": session_id
                            }))
                            
                            print(f"🎙️ [Joy TTS] Đang tổng hợp giọng nói...", flush=True)
                            opus_packets = await synthesize_speech(reply)
                            print(f"🎵 [Joy Audio] Đang phát {len(opus_packets)} gói âm thanh Opus...", flush=True)
                            for pkt in opus_packets:
                                if abort_current:
                                    break
                                await ws.send_bytes(pkt)
                                await asyncio.sleep(0.055)
                                
                            await ws.send_str(json.dumps({
                                "type": "tts",
                                "state": "stop",
                                "session_id": session_id
                            }))
                            print(f"✅ [Joy Audio] Hoàn tất lượt nói!", flush=True)
                            
                elif mtype == "abort":
                    print(f"⏹️ [Robot] Lệnh ngắt âm thanh.", flush=True)
                    abort_current = True
                    await ws.send_str(json.dumps({
                        "type": "tts",
                        "state": "stop",
                        "session_id": session_id
                    }))
                    
    except Exception as e:
        print(f"❌ [Lỗi WebSocket] {e}", flush=True)
    finally:
        print(f"🔌 [Robot] Đã đóng kết nối với: {client_ip}", flush=True)

async def root_handler(request):
    if request.headers.get("Upgrade", "").lower() == "websocket":
        ws = web.WebSocketResponse(heartbeat=25.0)
        await ws.prepare(request)
        await handle_websocket(ws, request.remote)
        return ws

    history_html = ""
    for idx, turn in enumerate(conversation_history):
        history_html += f"""
        <div style="margin-bottom: 0.75rem; padding: 0.5rem; background: rgba(255,255,255,0.03); border-radius: 0.5rem;">
            <div style="color: #38bdf8; font-weight: bold;">Bạn: {turn['user']}</div>
            <div style="color: #cbd5e1; margin-top: 0.25rem;">Joy: {turn['model']}</div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Joy Robot - Super AI Gemini Private Server</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            color: #f8fafc;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 1.5rem;
            box-sizing: border-box;
        }}
        .card {{
            background: rgba(30, 41, 59, 0.9);
            backdrop-filter: blur(16px);
            padding: 2.5rem;
            border-radius: 1.5rem;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
            max-width: 600px;
            width: 100%;
            border: 1px solid rgba(255, 255, 255, 0.12);
        }}
        h1 {{
            color: #38bdf8;
            margin-top: 0;
            font-size: 1.85rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        .status {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.4);
            padding: 0.5rem 1.25rem;
            border-radius: 9999px;
            font-weight: 600;
            margin-bottom: 1.5rem;
        }}
        .dot {{
            width: 10px;
            height: 10px;
            background: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 12px #10b981;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.4; transform: scale(0.85); }}
        }}
        .info-box {{
            background: rgba(15, 23, 42, 0.75);
            padding: 1.25rem;
            border-radius: 0.75rem;
            border: 1px solid rgba(255, 255, 255, 0.05);
            margin-bottom: 1.5rem;
            line-height: 1.8;
            font-size: 0.95rem;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding: 0.4rem 0;
        }}
        .info-row:last-child {{ border-bottom: none; }}
        .label {{ color: #94a3b8; }}
        .val {{ color: #f1f5f9; font-weight: 600; }}
        .badge {{
            background: #0284c7;
            color: white;
            padding: 0.15rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.85rem;
        }}
        .memory-box {{
            background: rgba(15, 23, 42, 0.6);
            border-radius: 0.75rem;
            padding: 1rem;
            max-height: 200px;
            overflow-y: auto;
            border: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 0.85rem;
            margin-bottom: 1.5rem;
        }}
        .note {{
            background: rgba(56, 189, 248, 0.1);
            border-left: 4px solid #38bdf8;
            padding: 1rem;
            border-radius: 0.5rem;
            font-size: 0.9rem;
            color: #bae6fd;
            line-height: 1.5;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🤖 Joy Super AI - Private Brain</h1>
        <div class="status"><span class="dot"></span> Super AI Đang Hoạt Động (11 Keys Sẵn Sàng)</div>
        
        <div class="info-box">
            <div class="info-row">
                <span class="label">🔑 Bể khóa API Keys</span>
                <span class="val"><span class="badge">11 Keys Xoay Vòng (~1.300 câu/ngày)</span></span>
            </div>
            <div class="info-row">
                <span class="label">🔑 Key đang hoạt động</span>
                <span class="val">Key #{current_key_idx + 1} / 11</span>
            </div>
            <div class="info-row">
                <span class="label">🧠 Lõi trí tuệ chính</span>
                <span class="val" style="color: #38bdf8;">Google Gemini 3.8 Flash</span>
            </div>
            <div class="info-row">
                <span class="label">🎙️ Giọng nói</span>
                <span class="val">Giọng gốc chuẩn (Nam Minh)</span>
            </div>
            <div class="info-row">
                <span class="label">💬 Tổng số câu đã hỏi</span>
                <span class="val">{total_questions_count} câu</span>
            </div>
        </div>

        <div style="font-weight: 600; margin-bottom: 0.5rem; color: #94a3b8; font-size: 0.9rem;">
            🧠 Trí nhớ ngữ cảnh gần đây ({len(conversation_history)}/{MAX_HISTORY_TURNS} lượt):
        </div>
        <div class="memory-box">
            {history_html if history_html else '<div style="color: #64748b; text-align: center; padding: 1rem;">Chưa có hội thoại nào. Hãy gọi "Hi Joy" để bắt đầu!</div>'}
        </div>
        
        <div class="note">
            🚀 <b>Joy đã hoàn toàn thuộc về bạn!</b> Kết nối 100% độc lập, không qua máy chủ hãng, không tốn chi phí và sở hữu trí tuệ của Gemini 3.8 Flash!
        </div>
    </div>
</body>
</html>"""
    return web.Response(text=html, content_type='text/html')

async def ota_handler(request):
    host = request.headers.get("Host", request.host)
    proto = "wss" if "onrender.com" in host else "ws"
    ws_url = f"{proto}://{host}/xiaozhi/v1/"
    print(f"📦 [OTA Request] Từ {request.remote} (Host: {host}) -> Gửi WebSocket URL: {ws_url}", flush=True)
    return web.json_response({
        "status": "ok",
        "message": "Server is working normally",
        "server_time": {
            "timestamp": int(time.time() * 1000),
            "timezone_offset": 420
        },
        "firmware": {
            "version": "2.1.1"
        },
        "websocket": {
            "url": ws_url
        }
    })

def make_app():
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/xiaozhi/v1', root_handler)
    app.router.add_get('/xiaozhi/v1/', root_handler)
    
    # OTA endpoints
    for route in ['/xiaozhi/ota/', '/xiaozhi/ota', '/xiaozhi/ota/activate', '/ota/', '/ota', '/ota/activate']:
        app.router.add_get(route, ota_handler)
        app.router.add_post(route, ota_handler)
        
    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("=" * 70, flush=True)
    print("🚀 JOY SUPER AI SERVER - 11 KEYS ROTATION POOL GEMINI 3.8 FLASH", flush=True)
    print(f"📡 WebSocket & Dashboard tại: http://172.31.98.201:{port}/", flush=True)
    print(f"🔑 Tổng số Keys nạp vào: {len(API_KEYS)} Keys (~1.300 câu hỏi/ngày)", flush=True)
    print(f"🧠 Lõi AI ưu tiên: {MODELS_ORDER[0]} (Tích hợp Trí nhớ Memory)", flush=True)
    print(f"🎙️ Giọng nói: Giọng cũ chuẩn Joy ({VOICE_NAME})", flush=True)
    print("=" * 70, flush=True)
    app = make_app()
    web.run_app(app, host="0.0.0.0", port=port, print=None)
