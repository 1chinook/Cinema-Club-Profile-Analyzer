import asyncio
import traceback
import time
import re
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from trivia import TRIVIA_LIST

app = FastAPI(title="Kadrajdaş | Kült Sinema Kulübü")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 600  # 10 dakika (saniye)

HTML_CONTENT = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kadrajdaş | Letterboxd Film Uyumu</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Space Grotesk', sans-serif; }
    .lb-green { color: #00e054; }
    .bg-lb-green { background-color: #00e054; }
    .trivia-fade { transition: opacity 0.3s ease-in-out; }
  </style>
</head>
<body class="bg-zinc-950 text-zinc-100 min-h-screen flex flex-col justify-between p-4 md:p-8">

  <header class="text-center py-4">
    <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-zinc-900 border border-zinc-800 text-xs text-zinc-400 mb-3">
      <span class="w-2 h-2 rounded-full bg-lb-green animate-pulse"></span>
      Kült Sinema Kulübü Film Eşleştirme Motoru
    </div>
    <h1 class="text-3xl md:text-5xl font-bold tracking-tight">Kadraj<span class="lb-green">daş</span></h1>
    <p class="text-zinc-400 text-sm mt-1">Letterboxd profillerinizin ortak kesitini ve puan uyumunu keşfedin.</p>
  </header>

  <main class="max-w-xl w-full mx-auto bg-zinc-900 border border-zinc-800 rounded-2xl p-6 shadow-2xl">
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
      <div>
        <label class="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">1. Kullanıcı</label>
        <div class="relative">
          <span class="absolute inset-y-0 left-0 flex items-center pl-3 text-zinc-500 text-sm">@</span>
          <input type="text" id="user1" placeholder="kullanici1" class="w-full bg-zinc-950 border border-zinc-700 rounded-xl pl-8 pr-3 py-2.5 text-sm focus:outline-none focus:border-green-500 transition">
        </div>
      </div>
      <div>
        <label class="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">2. Kullanıcı</label>
        <div class="relative">
          <span class="absolute inset-y-0 left-0 flex items-center pl-3 text-zinc-500 text-sm">@</span>
          <input type="text" id="user2" placeholder="kullanici2" class="w-full bg-zinc-950 border border-zinc-700 rounded-xl pl-8 pr-3 py-2.5 text-sm focus:outline-none focus:border-green-500 transition">
        </div>
      </div>
    </div>

    <button id="btnCompare" onclick="compareProfiles()" class="w-full py-3 bg-lb-green text-zinc-950 font-bold rounded-xl hover:bg-emerald-400 transition flex items-center justify-center gap-2">
      <span>Filmleri Karşılaştır</span>
    </button>

    <!-- Loading State & Trivia Box -->
    <div id="loader" class="hidden mt-6 text-center py-6">
      <div class="inline-block w-8 h-8 border-4 border-zinc-700 border-t-green-500 rounded-full animate-spin mb-3"></div>
      <div class="max-w-md mx-auto bg-zinc-950/60 border border-zinc-800 rounded-xl p-4 mt-2">
        <span class="text-[10px] font-bold text-zinc-500 uppercase tracking-widest block mb-1">Bunu Biliyor Muydunuz?</span>
        <p id="triviaText" class="text-xs text-zinc-300 leading-relaxed min-h-[36px] flex items-center justify-center trivia-fade">
          Kataloglar taranıyor...
        </p>
      </div>
    </div>

    <div id="errorAlert" class="hidden mt-4 p-3 bg-red-950/50 border border-red-800 text-red-300 text-xs rounded-xl"></div>

    <div id="resultCard" class="hidden mt-6 pt-6 border-t border-zinc-800">
      <div class="text-center mb-6">
        <span class="text-xs text-zinc-400 uppercase tracking-wider">Genel Sinema Uyumu</span>
        <div class="text-5xl font-black lb-green mt-1" id="scoreDisplay">0%</div>
        <span class="text-[11px] text-zinc-500 mt-1 block" id="timeDisplay"></span>
      </div>

      <div class="grid grid-cols-3 gap-2 bg-zinc-950 p-4 rounded-xl border border-zinc-800/80 text-center mb-6">
        <div>
          <div class="text-xs text-zinc-500">Ortak Film</div>
          <div class="text-lg font-bold mt-0.5" id="commonCountDisplay">0</div>
        </div>
        <div>
          <div class="text-xs text-zinc-500">Katalog Örtüşmesi</div>
          <div class="text-lg font-bold mt-0.5" id="overlapDisplay">0%</div>
        </div>
        <div>
          <div class="text-xs text-zinc-500">Puan Uyumu</div>
          <div class="text-lg font-bold mt-0.5" id="ratingScoreDisplay">0%</div>
        </div>
      </div>

      <div>
        <h3 class="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Ortak İzlenen Bazı Filmler</h3>
        <div id="filmsContainer" class="flex flex-wrap gap-1.5"></div>
      </div>
    </div>
  </main>

  <footer class="text-center text-xs text-zinc-600 py-4">
    by Kült Sinema Kulübü
  </footer>

  <script>
    /* TRIVIA_INJECTION_POINT */

    let triviaInterval = null;

    function startTrivia() {
      const elem = document.getElementById("triviaText");
      if (typeof TRIVIA_LIST === "undefined" || !TRIVIA_LIST || TRIVIA_LIST.length === 0) return;

      let lastIndex = Math.floor(Math.random() * TRIVIA_LIST.length);
      elem.innerText = TRIVIA_LIST[lastIndex];
      elem.style.opacity = "1";

      triviaInterval = setInterval(() => {
        elem.style.opacity = "0";
        setTimeout(() => {
          let nextIndex;
          do {
            nextIndex = Math.floor(Math.random() * TRIVIA_LIST.length);
          } while (nextIndex === lastIndex && TRIVIA_LIST.length > 1);
          lastIndex = nextIndex;
          
          elem.innerText = TRIVIA_LIST[nextIndex];
          elem.style.opacity = "1";
        }, 300);
      }, 3500);
    }

    function stopTrivia() {
      if (triviaInterval) {
        clearInterval(triviaInterval);
        triviaInterval = null;
      }
    }
  
    async function compareProfiles() {
      const u1 = document.getElementById("user1").value.trim();
      const u2 = document.getElementById("user2").value.trim();
      const errBox = document.getElementById("errorAlert");
      const loader = document.getElementById("loader");
      const resultCard = document.getElementById("resultCard");
      const btn = document.getElementById("btnCompare");

      errBox.classList.add("hidden");
      resultCard.classList.add("hidden");

      if (!u1 || !u2) {
        errBox.innerText = "Lütfen her iki kullanıcı adını da girin.";
        errBox.classList.remove("hidden");
        return;
      }

      btn.disabled = true;
      btn.classList.add("opacity-50", "cursor-not-allowed");
      loader.classList.remove("hidden");
      startTrivia();

      const startTime = performance.now();

      try {
        const response = await fetch("/api/match", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user1: u1, user2: u2 })
        });

        const data = await response.json();
        stopTrivia();
        loader.classList.add("hidden");
        btn.disabled = false;
        btn.classList.remove("opacity-50", "cursor-not-allowed");

        if (!data.success) {
          errBox.innerText = data.message || "Bir hata oluştu.";
          errBox.classList.remove("hidden");
          return;
        }

        const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);
        document.getElementById("timeDisplay").innerText = `Analiz süresi: ${elapsed} sn (${data.user1_total} ve ${data.user2_total} film)`;
        document.getElementById("scoreDisplay").innerText = `%${data.score}`;
        document.getElementById("commonCountDisplay").innerText = data.common_count;
        document.getElementById("overlapDisplay").innerText = `%${data.overlap_pct}`;
        document.getElementById("ratingScoreDisplay").innerText = `%${data.rating_pct}`;

        const listContainer = document.getElementById("filmsContainer");
        listContainer.innerHTML = "";
        data.sample_films.forEach(film => {
          const chip = document.createElement("span");
          chip.className = "px-2.5 py-1 bg-zinc-800 text-zinc-300 text-xs rounded-md border border-zinc-700/60";
          chip.innerText = film;
          listContainer.appendChild(chip);
        });

        resultCard.classList.remove("hidden");
      } catch (e) {
        stopTrivia();
        loader.classList.add("hidden");
        btn.disabled = false;
        btn.classList.remove("opacity-50", "cursor-not-allowed");
        errBox.innerText = "Sunucu bağlantı hatası oluştu.";
        errBox.classList.remove("hidden");
      }
    }
  </script>
</body>
</html>
"""

def extract_rating(element) -> float | None:
    if element is None:
        return None
    rating_elem = element.select_one("span.rating, p.poster-viewingdata span.rating, span.rating-micro")
    if rating_elem:
        for cls in rating_elem.get("class", []):
            if cls.startswith("rated-"):
                try:
                    return int(cls.split("-")[1]) / 2.0
                except (IndexError, ValueError):
                    pass
        text = rating_elem.get_text(strip=True)
        if text:
            stars = text.count("★") + (0.5 if "½" in text else 0)
            if stars > 0:
                return float(stars)
    return None

def parse_films_from_html(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    items = soup.select("ul.poster-list li, grid-item, li.poster-container")
    if not items:
        items = soup.select("div[data-film-slug], div[data-target-link]")

    page_films = {}
    for item in items:
        film_div = item if item.name == "div" and (item.get("data-film-slug") or item.get("data-target-link")) else item.find("div", attrs={"data-film-slug": True})
        if not film_div:
            film_div = item.find("div", attrs={"data-target-link": True})

        film_slug = None
        if film_div:
            film_slug = film_div.get("data-film-slug")
            if not film_slug:
                target = film_div.get("data-target-link", "")
                film_slug = target.strip("/").split("/")[-1] if target else None

        if not film_slug:
            link = item.find("a", href=True)
            if link and "/film/" in link["href"]:
                parts = link["href"].strip("/").split("/")
                if "film" in parts and len(parts) > parts.index("film") + 1:
                    film_slug = parts[parts.index("film") + 1]

        if not film_slug:
            continue

        rating = extract_rating(item)
        if rating is None and item.parent:
            rating = extract_rating(item.parent)

        page_films[film_slug] = rating

    return page_films

def extract_total_pages(html_text: str) -> int:
    soup = BeautifulSoup(html_text, "html.parser")
    paginate = soup.select("div.paginate-pages ul li a")
    max_p = 1
    for a in paginate:
        text = a.get_text(strip=True)
        if text.isdigit():
            max_p = max(max_p, int(text))
    return max_p

async def fetch_single_page(session: AsyncSession, username: str, page: int, sem: asyncio.Semaphore) -> dict:
    async with sem:
        url = f"https://letterboxd.com/{username}/films/page/{page}/"
        try:
            res = await session.get(url, timeout=12.0)
            if res.status_code == 200:
                return parse_films_from_html(res.text)
        except Exception:
            pass
        return {}

async def fetch_user_films_fast(username: str) -> dict:
    now = time.time()
    if username in USER_CACHE:
        cache_time, cached_data = USER_CACHE[username]
        if now - cache_time < CACHE_TTL:
            print(f"[{username}] Veriler önbellekten getirildi ({len(cached_data)} film).")
            return cached_data

    async with AsyncSession(impersonate="chrome124") as session:
        first_url = f"https://letterboxd.com/{username}/films/page/1/"
        try:
            res = await session.get(first_url, timeout=15.0)
            if res.status_code != 200:
                print(f"[{username}] 1. sayfa alınamadı. HTTP {res.status_code}")
                return {}
        except Exception as e:
            print(f"[{username}] Bağlantı hatası: {e}")
            return {}

        total_pages = extract_total_pages(res.text)
        all_films = parse_films_from_html(res.text)

        print(f"[{username}] Toplam {total_pages} sayfa tespit edildi. Paralel çekim başlatılıyor...")

        if total_pages > 1:
            sem = asyncio.Semaphore(4)
            tasks = [
                fetch_single_page(session, username, p, sem)
                for p in range(2, total_pages + 1)
            ]
            results = await asyncio.gather(*tasks)
            for page_dict in results:
                all_films.update(page_dict)

    print(f"==> [{username}] Çekim tamamlandı: Toplam {len(all_films)} film.")
    USER_CACHE[username] = (now, all_films)
    return all_films

class MatchRequest(BaseModel):
    user1: str
    user2: str

@app.get("/", response_class=HTMLResponse)
async def serve_home():
    rendered_html = HTML_CONTENT.replace(
        "/* TRIVIA_INJECTION_POINT */",
        f"const TRIVIA_LIST = {json.dumps(TRIVIA_LIST, ensure_ascii=False)};"
    )
    return HTMLResponse(content=rendered_html)

@app.post("/api/match")
async def api_match(payload: MatchRequest):
    try:
        u1 = payload.user1.strip().lower()
        u2 = payload.user2.strip().lower()

        if not u1 or not u2:
            return JSONResponse({"success": False, "message": "Kullanıcı adları boş bırakılamaz."})

        print(f"\n--- Turbo Karşılaştırma Talebi: {u1} vs {u2} ---")
        
        data1, data2 = await asyncio.gather(
            fetch_user_films_fast(u1),
            fetch_user_films_fast(u2)
        )

        set1, set2 = set(data1.keys()), set(data2.keys())
        if not set1 or not set2:
            return JSONResponse({
                "success": False, 
                "message": f"Kullanıcı verisi alınamadı. ({u1}: {len(set1)} film, {u2}: {len(set2)} film)"
            })

        common = set1.intersection(set2)
        min_size = min(len(set1), len(set2))
        overlap_ratio = len(common) / min_size if min_size > 0 else 0.0

        rated_common = [f for f in common if data1.get(f) is not None and data2.get(f) is not None]
        if rated_common:
            diffs = [abs(data1[f] - data2[f]) for f in rated_common]
            rating_score = 1.0 - (sum(diffs) / (len(rated_common) * 4.5))
        else:
            rating_score = 0.5

        final_score = round((0.4 * overlap_ratio + 0.6 * rating_score) * 100, 1)

        return JSONResponse({
            "success": True,
            "score": final_score,
            "overlap_pct": round(overlap_ratio * 100, 1),
            "rating_pct": round(rating_score * 100, 1),
            "common_count": len(common),
            "user1_total": len(set1),
            "user2_total": len(set2),
            "rated_count": len(rated_common),
            "sample_films": [f.replace("-", " ").title() for f in list(common)[:15]]
        })

    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"success": False, "message": f"Sunucu hatası: {str(e)}"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)