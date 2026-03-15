import requests
import xml.etree.ElementTree as ET
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import datetime
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer
import os

# ======================
# 配置
# ======================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
RECIPIENTS = os.getenv("RECIPIENTS", "").split(",")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SEARCH_TOPIC = os.getenv("SEARCH_TOPIC", "cognitive bias")
DISABLE_DEDUP = True

# ======================
# 数据库
# ======================
conn = sqlite3.connect("papers.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS papers(
id TEXT PRIMARY KEY,
title TEXT,
abstract TEXT,
source TEXT,
date TEXT
)
""")
conn.commit()

# ======================
# PubMed抓取（加容错）
# ======================
def fetch_pubmed():
    try:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"db": "pubmed", "term": SEARCH_TOPIC, "retmax": 20, "retmode": "json", "reldate": 1}
        r = requests.get(url, params=params, timeout=30)
        ids = r.json()["esearchresult"]["idlist"]
        papers = []
        if not ids:
            return papers
        url2 = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params2 = {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
        r2 = requests.get(url2, params=params2, timeout=30)
        root = ET.fromstring(r2.text)
        for article in root.findall(".//PubmedArticle"):
            title = article.findtext(".//ArticleTitle")
            abstract = article.findtext(".//AbstractText")
            pmid = article.findtext(".//PMID")
            if abstract:
                papers.append({"id": pmid, "title": title, "abstract": abstract, "source": "pubmed"})
        return papers
    except Exception as e:
        print("PubMed API error:", e)
        return []

# ======================
# arXiv抓取（24小时过滤）
# ======================
def fetch_arxiv():
    try:
        url = "http://export.arxiv.org/api/query"
        params = {"search_query": SEARCH_TOPIC, "start": 0, "max_results": 20, "sortBy": "submittedDate"}
        r = requests.get(url, params=params, timeout=30)
        root = ET.fromstring(r.text)
        papers = []
        for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
            published = entry.find("{http://www.w3.org/2005/Atom}published").text
            date = datetime.datetime.strptime(published[:10], "%Y-%m-%d").date()
            if (datetime.date.today() - date).days > 1:
                continue
            title = entry.find("{http://www.w3.org/2005/Atom}title").text
            abstract = entry.find("{http://www.w3.org/2005/Atom}summary").text
            pid = entry.find("{http://www.w3.org/2005/Atom}id").text
            papers.append({"id": pid, "title": title, "abstract": abstract, "source": "arxiv"})
        return papers
    except Exception as e:
        print("arXiv API error:", e)
        return []

# ======================
# 数据库存储
# ======================
def save_papers(papers):
    new_papers = []
    for p in papers:
        try:
            cursor.execute(
                "INSERT INTO papers VALUES (?,?,?,?,?)",
                (p["id"], p["title"], p["abstract"], p["source"], str(datetime.date.today()))
            )
            new_papers.append(p)
        except:
            pass
    conn.commit()
    return new_papers

# ======================
# AI理解（评分+摘要一次完成）
# ======================
def analyze_paper(title, abstract):
    if not DEEPSEEK_API_KEY:
        return 5, "未配置API Key"
    prompt = f"""
请分析下面论文：

标题：
{title}

摘要：
{abstract}

输出格式：

评分: 1-10

研究问题:
核心发现:
研究方法:
"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}]}
    r = requests.post(url, headers=headers, json=data, timeout=60)
    result = r.json()
    text = result["choices"][0]["message"]["content"]
    try:
        score = int(text.split("评分")[1].split("\n")[0].replace(":", "").strip())
    except:
        score = 5
    return score, text

# ======================
# AI趋势综述
# ======================
def summarize_trends(papers):
    if not papers or not DEEPSEEK_API_KEY:
        return ""
    abstracts = "\n\n".join([p["abstract"] for p in papers[:20]])
    prompt = f"""
下面是最近论文摘要：

{abstracts}

请总结：

1 当前研究热点
2 常见研究方法
3 未来方向

150字以内中文。
"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}]}
    r = requests.post(url, headers=headers, json=data, timeout=60)
    result = r.json()
    return result["choices"][0]["message"]["content"]

# ======================
# 趋势图
# ======================
def trend_analysis():
    cursor.execute("SELECT abstract FROM papers")
    texts = [row[0] for row in cursor.fetchall()]
    if len(texts) < 10:
        return None
    vectorizer = TfidfVectorizer(stop_words="english", max_features=15)
    X = vectorizer.fit_transform(texts)
    words = vectorizer.get_feature_names_out()
    scores = X.sum(axis=0).tolist()[0]
    plt.figure()
    plt.bar(words, scores)
    plt.xticks(rotation=60)
    plt.title("Research Trends")
    plt.tight_layout()
    file = "trend.png"
    plt.savefig(file)
    return file

# ======================
# 邮件
# ======================
def send_email(report, trend_file, paper_count):
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("未配置邮箱")
        return
    msg = MIMEMultipart()
    msg["Subject"] = f"心理学研究雷达（{paper_count}篇新论文）"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(report, "plain", "utf-8"))
    if trend_file:
        with open(trend_file, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-Disposition", "attachment", filename="trend.png")
            msg.attach(img)
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    server.sendmail(EMAIL_ADDRESS, RECIPIENTS, msg.as_string())
    server.quit()

# ======================
# 主程序
# ======================
def main():
    papers = []
    try:
        papers += fetch_pubmed()
    except:
        print("PubMed fetch failed, continue...")
    try:
        papers += fetch_arxiv()
    except:
        print("arXiv fetch failed, continue...")

    if DISABLE_DEDUP:
        new_papers = papers
    else:
        papers = list({p["id"]: p for p in papers}.values())
        new_papers = save_papers(papers)

    report = "心理学研究雷达（过去24小时）\n\n"

    if not new_papers:
        report += "今天没有发现新的论文。\n\n"

    else:
        for p in new_papers:
            score, summary = analyze_paper(p["title"], p["abstract"])
            p["score"] = score
            p["summary"] = summary

        new_papers = sorted(new_papers, key=lambda x: x["score"], reverse=True)
        trend_summary = summarize_trends(new_papers)
        report += "今日研究趋势综述\n"
        report += trend_summary + "\n\n"
        report += "========================\n\n"

        for p in new_papers:
            report += f"评分：{p['score']}/10\n"
            report += f"论文：{p['title']}\n\n"
            report += p["summary"] + "\n\n"
            if p["source"] == "pubmed":
                link = f"https://pubmed.ncbi.nlm.nih.gov/{p['id']}"
            else:
                link = p["id"]
            report += f"原文链接：{link}\n"
            report += "\n------------------------\n\n"

    trend_file = trend_analysis()

    # ======================
    # 邮件发送策略
    # ======================
    now = datetime.datetime.utcnow()
    china_hour = (now.hour + 8) % 24
    paper_count = len(new_papers)

    if paper_count > 0:
        print("发现新论文，发送邮件")
        send_email(report, trend_file, paper_count)
    elif china_hour == 9:
        print("每日9点日报")
        send_email(report, trend_file, paper_count)
    else:
        print("没有新论文，跳过发送")

if __name__ == "__main__":
    main()
