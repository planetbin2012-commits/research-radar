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

RECIPIENTS = os.getenv("RECIPIENTS","").split(",")

SMTP_SERVER = os.getenv("SMTP_SERVER","smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT",587))

SEARCH_TOPIC = os.getenv("SEARCH_TOPIC","cognitive bias")

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

# PubMed抓取

# ======================

def fetch_pubmed():

```
url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

params={
    "db":"pubmed",
    "term":SEARCH_TOPIC,
    "retmax":20,
    "retmode":"json",
    "reldate":1
}

r=requests.get(url,params=params)

ids=r.json()["esearchresult"]["idlist"]

papers=[]

if not ids:
    return papers

url2="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

params2={
    "db":"pubmed",
    "id":",".join(ids),
    "retmode":"xml"
}

r2=requests.get(url2,params=params2)

root=ET.fromstring(r2.text)

for article in root.findall(".//PubmedArticle"):

    title=article.findtext(".//ArticleTitle")
    abstract=article.findtext(".//AbstractText")
    pmid=article.findtext(".//PMID")

    if abstract:

        papers.append({
            "id":pmid,
            "title":title,
            "abstract":abstract,
            "source":"pubmed"
        })

return papers
```

# ======================

# arXiv抓取（24小时过滤）

# ======================

def fetch_arxiv():

```
url="http://export.arxiv.org/api/query"

params={
    "search_query":SEARCH_TOPIC,
    "start":0,
    "max_results":20,
    "sortBy":"submittedDate"
}

r=requests.get(url,params=params)

root=ET.fromstring(r.text)

papers=[]

for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):

    published = entry.find("{http://www.w3.org/2005/Atom}published").text
    date = datetime.datetime.strptime(published[:10], "%Y-%m-%d").date()

    if (datetime.date.today() - date).days > 1:
        continue

    title=entry.find("{http://www.w3.org/2005/Atom}title").text
    abstract=entry.find("{http://www.w3.org/2005/Atom}summary").text
    pid=entry.find("{http://www.w3.org/2005/Atom}id").text

    papers.append({
        "id":pid,
        "title":title,
        "abstract":abstract,
        "source":"arxiv"
    })

return papers
```

# ======================

# 数据库存储 + 去重

# ======================

def save_papers(papers):

```
new_papers=[]

for p in papers:

    try:

        cursor.execute(
            "INSERT INTO papers VALUES (?,?,?,?,?)",
            (
                p["id"],
                p["title"],
                p["abstract"],
                p["source"],
                str(datetime.date.today())
            )
        )

        new_papers.append(p)

    except:
        pass

conn.commit()

return new_papers
```

# ======================

# AI摘要

# ======================

def summarize_paper(title,abstract):

```
if not DEEPSEEK_API_KEY:
    return "未配置 DeepSeek API Key"

prompt=f"""
```

请用中文总结下面论文：

标题：
{title}

摘要：
{abstract}

输出三行：

研究问题：
核心发现：
研究方法：
"""

```
url="https://api.deepseek.com/v1/chat/completions"

headers={
    "Authorization":f"Bearer {DEEPSEEK_API_KEY}",
    "Content-Type":"application/json"
}

data={
    "model":"deepseek-chat",
    "messages":[{"role":"user","content":prompt}]
}

r=requests.post(url,headers=headers,json=data)

result=r.json()

return result["choices"][0]["message"]["content"]
```

# ======================

# 趋势图

# ======================

def trend_analysis():

```
cursor.execute("SELECT abstract FROM papers")

texts=[row[0] for row in cursor.fetchall()]

if len(texts)<10:
    return None

vectorizer=TfidfVectorizer(stop_words="english",max_features=15)

X=vectorizer.fit_transform(texts)

words=vectorizer.get_feature_names_out()

scores=X.sum(axis=0).tolist()[0]

plt.figure()

plt.bar(words,scores)

plt.xticks(rotation=60)

plt.title("Research Trends")

plt.tight_layout()

file="trend.png"

plt.savefig(file)

return file
```

# ======================

# 发送邮件

# ======================

def send_email(report,trend_file):

```
if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
    print("未配置邮箱")
    return

msg=MIMEMultipart()

msg["Subject"]="心理学研究雷达（过去24小时）"

msg["From"]=EMAIL_ADDRESS
msg["To"]=", ".join(RECIPIENTS)

msg.attach(MIMEText(report,"plain","utf-8"))

if trend_file:

    with open(trend_file,"rb") as f:

        img=MIMEImage(f.read())

        img.add_header(
            'Content-Disposition',
            'attachment',
            filename="trend.png"
        )

        msg.attach(img)

server=smtplib.SMTP(SMTP_SERVER,SMTP_PORT)

server.starttls()

server.login(EMAIL_ADDRESS,EMAIL_PASSWORD)

server.sendmail(
    EMAIL_ADDRESS,
    RECIPIENTS,
    msg.as_string()
)

server.quit()
```

# ======================

# 主程序

# ======================

def main():

```
papers=[]

papers+=fetch_pubmed()
papers+=fetch_arxiv()

# 第二层去重（内存ID去重）
papers=list({p["id"]:p for p in papers}.values())

new_papers=save_papers(papers)

if not new_papers:
    print("今天没有新论文")
    return

report="心理学研究雷达（过去24小时）\n\n"

for p in new_papers:

    summary=summarize_paper(p["title"],p["abstract"])

    report+=f"论文：{p['title']}\n\n"
    report+=summary+"\n\n"

    if p["source"]=="pubmed":
        link=f"https://pubmed.ncbi.nlm.nih.gov/{p['id']}"
    else:
        link=p["id"]

    report+=f"原文链接：{link}\n"
    report+="\n------------------------\n\n"

trend_file=trend_analysis()

print(report)

send_email(report,trend_file)
```

if **name**=="**main**":
main()
