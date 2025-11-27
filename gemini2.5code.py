import os
import json
import re
import copy
from typing_extensions import TypedDict
import PIL.Image
from dotenv import load_dotenv
import google.generativeai as genai
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvas
from IPython.display import Image as IPImage, display


# --- API KEY ---
# Load .env
load_dotenv()
# Ambil API key dari environment
api_key = os.getenv("GOOGLE_API_KEY")
# Konfigurasi API key
genai.configure(api_key=api_key, transport="rest")


# --- DEFINISI STRUKTUR DATA ---
class MetaData(TypedDict):
    Year: int
    StationNumber: int
    Location: str
    County: str
    River_basin: str
    Type_of_gauge: str
    Observer: str

class Monthly(TypedDict):
    Month: str
    rainfall: str

class Annual(TypedDict):
    Year: int
    rainfall: list[Monthly]

class Decadal(TypedDict):
    rainfall: list[Annual]

class Totals(TypedDict):
    Totals: list[str]
    
# INPUT GAMBAR
img_path = r"C:\Users\Michelle\scratch\everydata\split\val\images\ABERSYCHAN-GLANSYCHAN_ABERSYCHAN-GLANSYCHAN_page1.png"
img = PIL.Image.open(img_path)    


# PEMANGGILAN MODEL GEMINI
model = genai.GenerativeModel("gemini-2.5-flash-preview-09-2025")

# ---- Extract Metadata ----
result = model.generate_content(
    [img, "\n\n", "List the station metadata"],
    generation_config=genai.GenerationConfig(
        response_mime_type="application/json", response_schema=MetaData
    ),
)
with open("metadata2.5.json", "w") as f:
    f.write(result.text)

# ---- Extract Monthly Observations ----
prompt = (
    "List the monthly rainfall observations from the image. "
    "The table likely covers around 10 consecutive years (e.g., 1890–1899). "
    "If some years are missing or unclear, still include them with rainfall='-' "
    "and include all 12 months (January–December)."
)

result = model.generate_content(
    [img, "\n\n", prompt],
    generation_config=genai.GenerationConfig(
        response_mime_type="application/json",
        response_schema=Decadal
    ),
)

with open("monthly2.5.json", "w") as f:
    f.write(result.text)


# ---- Extract Totals ----
result = model.generate_content(
    [img, "\n\n", "List the annual totals."],
    generation_config=genai.GenerationConfig(
        response_mime_type="application/json", response_schema=Totals
    ),
)
with open("totals2.5.json", "w") as f:
    f.write(result.text)
    
# --- Data Cleaning ---
def normalize_rainfall_value(val: str):
    """Bersihkan dan normalisasi angka curah hujan dari string OCR."""
    if val is None:
        return "-"

    # Hilangkan spasi dan karakter whitespace
    val = str(val).strip().replace(" ", "")
    if val == "" or val in ["-", "–", "—"]:
        return "-"

    # Perbaiki kesalahan OCR umum (huruf ke angka)
    val = val.replace("O", "0").replace("o", "0")
    val = val.replace("l", "1").replace("I", "1")

    # Ganti karakter pemisah aneh jadi titik
    val = val.replace("-", ".").replace(":", ".").replace("'", ".").replace(",", ".").replace("_", ".")

    # Hapus semua karakter selain angka & titik
    val = re.sub(r"[^0-9.]", "", val)

    # Jika kosong setelah dibersihkan
    if val == "":
        return "-"

    # Lebih dari satu titik → ambil hanya yang pertama
    parts = val.split(".")
    if len(parts) > 2:
        val = parts[0] + "." + parts[1]

    # Tidak ada titik tapi terlalu panjang (contoh "444" → "4.44")
    if val.isdigit() and len(val) >= 3:
        val = val[0] + "." + val[1:]

    # Angka diawali titik → tambah 0 (contoh ".66" → "0.66")
    if val.startswith("."):
        val = "0" + val

    # Angka diakhiri titik → hapus titik (contoh "44." → "44")
    if val.endswith("."):
        val = val[:-1]

    # Konversi ke float jika bisa
    try:
       num= round(float(val), 2)
       if num == 0.0:
           return "-"
       return num
    except ValueError:
        return "-"


def clean_gemini_json(data, expected_years=None, metadata=None, total_years=10):
    """
    Membersihkan JSON hasil Gemini Vision, menormalkan nilai curah hujan,
    menambahkan bulan kosong bila hilang, dan menjaga urutan.
    Tidak mengasumsikan tahun default (menyesuaikan dari data input).
    """
    import copy
    data_clean = copy.deepcopy(data)
    rainfall_data = data_clean.get("rainfall", [])

    base_months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    
    # --- Deteksi tahun dari data (jika expected_years tidak diberikan) ---
    if expected_years is None:
        detected_years = sorted({
            y.get("Year") for y in rainfall_data if isinstance(y.get("Year"), int)
        })
    else:
        detected_years = expected_years

    complete_rainfall = []
    for year in detected_years:
        year_block = next((y for y in rainfall_data if y.get("Year") == year), None)
        month_map = {m.get("Month"): m for m in (year_block.get("rainfall", []) if year_block else [])}

        fixed_months = []
        for m in base_months:
            if m in month_map:
                val = month_map[m].get("rainfall", "-")
                fixed_months.append({
                    "Month": m,
                    "rainfall": normalize_rainfall_value(val)
                })
            else:
                fixed_months.append({"Month": m, "rainfall": "-"})

        complete_rainfall.append({"Year": year, "rainfall": fixed_months})

    data_clean["rainfall"] = complete_rainfall
    return data_clean

def clean_totals_json(data, monthly_data=None, tol_abs=0.5, tol_rel=0.05):

    data_clean = copy.deepcopy(data)
    totals_raw = data_clean.get("Totals", [])
    cleaned_totals = [normalize_rainfall_value(v) for v in totals_raw]

    # fallback simple: jika monthly_data tidak ada, buat mapping indeks
    if not monthly_data or "rainfall" not in monthly_data:
        if not cleaned_totals:
            return {"Totals": []}
        # fallback: map left->right to synthetic years (1..N)
        n = len(cleaned_totals)
        return {"Totals": [{"Year": i + 1, "Total": cleaned_totals[i]} for i in range(n)]}

    # build year list and monthly sums
    year_blocks = monthly_data["rainfall"]
    year_list = [yb["Year"] for yb in year_blocks]

    monthly_sums = {}
    years_with_data = []
    for yb in year_blocks:
        year = yb["Year"]
        months = yb.get("rainfall", [])
        vals = []
        for m in months:
            v = m.get("rainfall")
            if v in ("-", None, ""):
                continue
            try:
                vals.append(float(v))
            except Exception:
                # already normalized in monthly cleaning, but safe fallback
                try:
                    vals.append(float(str(v).replace(",", ".")))
                except Exception:
                    pass
        if vals:
            monthly_sums[year] = round(sum(vals), 2)
            years_with_data.append(year)
        else:
            monthly_sums[year] = None  # no data

    # prepare aligned list initial filled with "-"
    aligned = ["-"] * len(year_list)

    # keep track of which years already assigned
    assigned_years = set()

    # 1) Try exact / nearest numeric matching for each cleaned_total (in OCR order)
    for tot in cleaned_totals:
        if tot == "-" or tot is None:
            # skip empty total (no mapping)
            continue

        best_year = None
        best_diff = None
        for year in years_with_data:
            if year in assigned_years:
                continue
            sum_val = monthly_sums.get(year)
            if sum_val is None:
                continue
            diff = abs(sum_val - tot)
            rel = diff / (sum_val if sum_val != 0 else (tot if tot != 0 else 1))
            # choose smallest diff
            if (best_diff is None) or (diff < best_diff):
                best_diff = diff
                best_year = year

        # accept best match only if within tolerances
        if best_year is not None:
            # check tolerances before assigning
            if best_diff is not None and (best_diff <= tol_abs):
                idx = year_list.index(best_year)
                aligned[idx] = tot
                assigned_years.add(best_year)
                continue
            else:
                # also allow relative tolerance
                sum_val = monthly_sums.get(best_year, 0) or 0
                rel = best_diff / (sum_val if sum_val != 0 else 1)
                if rel <= tol_rel:
                    idx = year_list.index(best_year)
                    aligned[idx] = tot
                    assigned_years.add(best_year)
                    continue
        # if no acceptable numeric match, we'll defer to order-based mapping below
        # (mark this total as "unmapped" for now)
    # 2) Map remaining (unmapped) totals to years_with_data left->right skipping assigned ones
    unmapped_totals = []
    for tot in cleaned_totals:
        # consider only totals not already placed (value not present in aligned)
        # but careful to count duplicates => we compare by identity of placement
        # simplest: if tot is present in aligned as value, assume mapped (works for floats/strings)
        if tot == "-" or tot is None:
            continue
        if any(a == tot for a in aligned):
            continue
        unmapped_totals.append(tot)

    # assign unmapped totals sequentially to remaining years_with_data
    remaining_years = [y for y in years_with_data if y not in assigned_years]
    for i, tot in enumerate(unmapped_totals):
        if i < len(remaining_years):
            year = remaining_years[i]
            idx = year_list.index(year)
            aligned[idx] = tot
            assigned_years.add(year)
        else:
            # no years left — ignore extras
            break

    # final assembly: pair year_list with aligned totals
    totals_with_year = []
    for year, val in zip(year_list, aligned):
        totals_with_year.append({"Year": year, "Total": val})

    return {"Totals": totals_with_year}

# ---- Bersihkan monthly.json ----
with open("monthly2.5.json", "r") as f:
    mo_raw = json.load(f)

mo_cleaned = clean_gemini_json(mo_raw)

with open("monthly_cleaned2.5.json", "w") as f:
    json.dump(mo_cleaned, f, indent=2)    
    
# ---- Bersihkan totals.json ----
with open("totals2.5.json", "r") as f:
    totals_raw = json.load(f)

totals_cleaned = clean_totals_json(totals_raw, monthly_data=mo_cleaned)

with open("totals_cleaned2.5.json", "w") as f:
    json.dump(totals_cleaned, f, indent=2)


# ---- Extract Metadata ----
result = model.generate_content(
    [
        img,
        """
        Extract the station metadata from the rainfall register image.

        Output as JSON using this schema:
        {
        station :
        {
          "StationNumber": int | null,
          "Location": string,
          "County": string,
          "River_basin": string | null,
          "Type_of_gauge": string | null,
          "Observer": string
        }}

        Notes:
        - Location appears after "RAIN FALL AT".
        - County is after "County of".
        - Observer name appears after "Observer".
        - If any numeric value is unclear or missing, use null.
        """

    ],
    generation_config=genai.GenerationConfig(
        response_mime_type="application/json"
    ),
)
with open("metadata_cleaned2.5.json", "w") as f:
    f.write(result.text)


# load the image
img = PIL.Image.open(r"C:\Users\Michelle\scratch\everydata\split\val\images\ABERSYCHAN-GLANSYCHAN_ABERSYCHAN-GLANSYCHAN_page1.png")

# load the digitised data
metadata = json.load(open("metadata_cleaned2.5.json"))
mo = json.load(open("monthly_cleaned2.5.json"))
totals = json.load(open("totals_cleaned2.5.json"))

# Create the figure
fig = Figure(
    figsize=(13, 10),  # Width, Height (inches)
    dpi=100,
    facecolor=(0.95, 0.95, 0.95, 1),
    edgecolor=None,
    linewidth=0.0,
    frameon=True,
    subplotpars=None,
    tight_layout=None,
)
canvas = FigureCanvas(fig)

# Image in the left
ax_original = fig.add_axes([0.01, 0.02, 0.47, 0.96])
ax_original.set_axis_off()
imgplot = ax_original.imshow(img, zorder=10)


station = metadata["station"]

# Metadata top right
ax_metadata = fig.add_axes([0.52, 0.8, 0.47, 0.15])
ax_metadata.set_xlim(0, 1)
ax_metadata.set_ylim(0, 1)
ax_metadata.set_xticks([])
ax_metadata.set_yticks([])


ax_metadata.text(
    0.05,
    0.8,
    f"Station Number: {station.get('StationNumber', '-')}",
    fontsize=12,
    color="black",
)

ax_metadata.text(
    0.05,
    0.7,
    f"Location: {station.get('Location', '-')}",
    fontsize=12,
    color="black",
)
ax_metadata.text(
    0.05,
    0.6,
    f"Observer: {station.get ('Observer', '-')}",
    fontsize=12,
    color="black",
)
ax_metadata.text(
    0.05,
    0.5,
    f"County: {station.get ('County', '-')}",
    fontsize=12,
    color="black",
)
ax_metadata.text(
    0.05,
    0.4,
    f"River Basin: {station.get ('River_basin', '-')}",
    fontsize=12,
    color="black",
)
ax_metadata.text(
    0.05,
    0.3,
    f"Type of Gauge:{station.get ('Type_of_gauge', '-')}",
    fontsize=12,
    color="black",
)

years = []
for year in mo["rainfall"]:
    years.append(year["Year"])
years = sorted(years)

# Digitised numbers on the right
ax_digitised = fig.add_axes([0.52, 0.13, 0.47, 0.63])
ax_digitised.set_xlim(years[0] - 0.5, years[-1] + 0.5)
ax_digitised.set_xticks(range(years[0], years[-1] + 1))
ax_digitised.set_xticklabels(years)
ax_digitised.set_ylim(0.5, 12.5)
ax_digitised.set_yticks(range(1, 13))
ax_digitised.set_yticklabels(
    (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
)
ax_digitised.xaxis.set_ticks_position("top")
ax_digitised.xaxis.set_label_position("top")
ax_digitised.invert_yaxis()
ax_digitised.set_aspect("auto")

monthNumbers = {
    "Jan": 1,
    "January": 1,
    "Feb": 2,
    "February": 2,
    "Mar": 3,
    "March": 3,
    "Apr": 4,
    "April": 4,
    "May": 5,
    "Jun": 6,
    "June": 6,
    "Jul": 7,
    "July": 7,
    "Aug": 8,
    "August": 8,
    "Sep": 9,
    "September": 9,
    "Oct": 10,
    "October": 10,
    "Nov": 11,
    "November": 11,
    "Dec": 12,
    "December": 12,
}
for year in mo["rainfall"]:
    for month in year["rainfall"]:
        ax_digitised.text(
            year["Year"],
            monthNumbers[month["Month"]],
            month["rainfall"],
            ha="center",
            va="center",
            fontsize=12,
            color="black",
        )


# Totals along the bottom
# Samakan skala sumbu X dengan tabel utama (pakai tahun, bukan indeks)
ax_totals = fig.add_axes([0.52, 0.09, 0.47, 0.03])

ax_totals.set_xlim(years[0] - 0.5, years[-1] + 0.5)
ax_totals.set_xticks(range(years[0], years[-1] + 1))
ax_totals.set_xticklabels([])  # supaya tidak menampilkan tahun dua kali
ax_totals.set_ylim(0, 1)
ax_totals.set_yticks([])

# Tampilkan angka total sesuai tahun
for t in totals["Totals"]:
    year = t["Year"]
    total_val = t["Total"]

    if year in years:  # pastikan hanya tahun yang tampil di tabel
        ax_totals.text(
            year,
            0.5,
            str(total_val),
            ha="center",
            va="center",
            fontsize=12,
            color="black",
        )
# Render
fig.savefig(
    "gemini2.5.webp",
)