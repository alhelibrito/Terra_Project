[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/alhelibrito/Terra_Project/blob/main/PDSI_pentads_to_monthly_Des_Moines_2022_2025.ipynb)

# Terra_Project: PDSI Resampling & Trend Analysis

This project focuses on the **temporal resampling** of high-resolution climate data (gridMET) and the identification of **seasonal drought trends** in West Des Moines, Iowa (2022-2025).

### **Core Objectives:**
* **Data Resampling:** Aggregating 5-day pentad resolution into monthly arithmetic means for climate monitoring.
* **Trend Visualization:** Identifying seasonal variations in the Palmer Drought Severity Index (PDSI) using standardized classification thresholds.

### **Latest Analysis Result:**
![Monthly PDSI Analysis](output_files/Monthly%20PDSI%20analysis.png)
*Figure 1: High-contrast visualization of monthly PDSI trends, highlighting the rapid hydrological shifts observed in 2025.*

### **Methodology & Standards:**
Data processing is performed via **Python (Pandas/Seaborn)**. To ensure international scientific alignment, visualization thresholds follow the standardized **Palmer Drought Severity Index** categories:
* **<-3.0**: Severe/Extreme Drought (Brown)
* **-2.0 to -2.9**: Moderate Drought (Orange)
* **-1.9 to 1.9**: Near Normal (Neutral)
* **>2.0**: Unusually Moist (Green)

### **Repository Contents:**
* **Input:** [`pentads_pdsi_wdm_2022_2025.csv`](input_files/pentads_pdsi_wdm_2022_2025.csv) — Original 5-day resolution data.
* **Notebook:** [`PDSI_pentads_to_monthly_Des_Moines_2022_2025.ipynb`](notebooks/PDSI_pentads_to_monthly_Des_Moines_2022_2025.ipynb) — Main processing pipeline (Cleaning  → Resampling → Plotting).
* **Output:** [`monthly_pdsi_wdm_2022_2025.csv`](output_files/monthly_pdsi_wdm_2022_2025.csv) — Final processed monthly dataset.

---

## Local Development Setup

### Prerequisites
- **Python 3** installed and available as `python3`.
- **VS Code** with the **Jupyter** and **Python** extensions.

### One-time setup
From the project root, run:
```bash
bash init.sh
