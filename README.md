### 🌧️ Rainfall Table Extractor
A Streamlit app that extracts, cleans, and visualizes **10-year monthly rainfall tables** from images using **OCR (Gemini)**.  
The app automatically generates **JSON outputs**, **cleaned rainfall tables**, and **rainfall plots** for analysis.

This project was inspired and learned from:  
🔗 https://github.com/philip-brohan/AI_daily_precip

---

### 🚀 Features

#### ✅ **1. OCR Extraction (Gemini)**
Uses **Gemini 2.5-Flash-Preview-09-2025** to extract:
- Metadata (station name, country, etc.)
- Monthly rainfall values (10 years)
- Totals

#### ✅ **2. Interactive Streamlit Dashboard**
Includes:
- Image preview  
- Automatic image validation  
- Extraction progress bar  
- Downloadable JSON outputs  
- Clean rainfall visualizations  
- Built-in plot generator  

#### ✅ **3. Outputs**
The app generates:
- `metadata.json`
- `monthly.json`
- `totals.json`
- `rainfall_plot.png`

---

#### 🧠 Model Used
This app uses:

**Gemini 2.5-Flash-Preview-09-2025**  
for all OCR and extraction steps (metadata + monthly + totals).

## 📁 Project Structure

