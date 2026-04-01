[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/alhelibrito/Terra_Project/blob/main/PDSI_pentads_to_monthly_Des_Moines_2022_2025.ipynb)

# Terra_Project: PDSI Resampling & Trend Analysis

This project focuses on the **temporal resampling** of high-resolution climate data (gridMET) and the identification of **seasonal drought trends** in West Des Moines, Iowa (2022-2025).

### **Core Objectives:**
* **Data Resampling:** Aggregating 5-day pentad resolution into monthly arithmetic means for climate monitoring.
* **Trend Visualization:** Identifying seasonal variations in the Palmer Drought Severity Index (PDSI) over a 3-year period.

### **Repository Contents:**
* **Input:** [`pentads_pdsi_wdm_2022_2025.csv`](https://raw.githubusercontent.com/alhelibrito/Terra_Project/main/pentads_pdsi_wdm_2022_2025.csv) — Original 5-day resolution data.
* **Notebook:** [`PDSI_pentads_to_monthly_Des_Moines_2022_2025.ipynb`](https://github.com/alhelibrito/Terra_Project/blob/main/PDSI_pentads_to_monthly_Des_Moines_2022_2025.ipynb) — Processing script (Cleaning + Resampling + Plotting).
* **Output:** [`monthly_pdsi_wdm_2022_2025.csv`](https://raw.githubusercontent.com/alhelibrito/Terra_Project/main/monthly_pdsi_wdm_2022_2025.csv) — Final processed monthly dataset.

### **Methodology:**
The notebook utilizes **Pandas** for time-series manipulation, converting high-frequency meteorological data into standardized monthly indicators to facilitate the identification of drought persistence and recovery phases.

---

