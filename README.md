# FlexiBFT 🔐  
Adaptive Byzantine Fault Tolerant Consensus Framework  

---

## 📌 Overview

FlexiBFT is a team-developed Python framework designed to experiment with Flexible Byzantine Fault Tolerance (BFT) mechanisms in distributed systems.  

The project provides a modular environment for simulating consensus behavior under varying fault assumptions and quorum configurations. It is intended for academic exploration and distributed systems research experimentation.

---

## 🧠 Motivation

Traditional Byzantine Fault Tolerant systems typically require fixed quorum rules (e.g., 2f + 1 nodes to tolerate f faults).  

FlexiBFT explores:

- Adjustable quorum thresholds  
- Flexible fault tolerance configurations  
- Simulation of Byzantine failure scenarios  
- Safety and consensus behavior under dynamic fault models  

This allows experimentation with adaptive consensus strategies beyond classical BFT assumptions.

---

## 🚀 Key Features

- Modular consensus architecture  
- Configurable number of nodes and fault thresholds  
- Simulation of Byzantine fault scenarios  
- Extensible framework for distributed systems experimentation  
- Clean and structured Python implementation  

---

## 📂 Repository Structure

```
flexible_bft/
│── core/              # Core consensus logic
│── app.py             # Simulation entry point
│── static/            # Supporting resources
│── requirements.txt   # Project dependencies
```

---

## ⚙️ Installation

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/satyamnarayan14/flexible_bft.git
cd flexible_bft
```

### 2️⃣ Create Virtual Environment

```bash
python -m venv venv
```

Activate it:

- Windows:
```bash
venv\Scripts\activate
```

- Mac/Linux:
```bash
source venv/bin/activate
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

## ▶️ Running the Simulation

```bash
python app.py
```

Simulation parameters such as:
- Number of nodes  
- Fault thresholds  
- Quorum configurations  
- Failure scenarios  

can be modified within the application logic.

---

## 🧪 Research Applications

This framework can be extended to:

- Compare flexible vs classical BFT quorum systems  
- Simulate crash and Byzantine faults  
- Evaluate consensus reliability under adversarial behavior  
- Measure scalability and performance trade-offs  
- Integrate logging and benchmarking modules  

---

## 📌 Future Improvements

- Performance benchmarking tools  
- Network simulation abstraction  
- Visualization dashboard  
- Asynchronous consensus modeling  
- Advanced fault injection mechanisms  

---

## 📄 License

Add your preferred license (MIT or Apache 2.0 recommended).
