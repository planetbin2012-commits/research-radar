

# Paper Bot — 心理学研究雷达

自动抓取心理学最新论文，生成中文摘要、AI评分和趋势分析，通过邮件发送简报。

---

## 功能

* 来源：PubMed + arXiv（过去24小时新增论文）
* 自动中文摘要 + AI评分（1-10）
* 趋势分析：关键词图 + 研究热点小综述
* 邮件通知：新论文立即发；无新论文每天9点发日报
* 支持多收件人，自动去重（可关闭）

---

## 配置环境变量

```text
DEEPSEEK_API_KEY  # DeepSeek API Key
EMAIL_ADDRESS     # 发件邮箱
EMAIL_PASSWORD    # 邮箱授权码
RECIPIENTS        # 收件人，用英文逗号分隔
SEARCH_TOPIC      # 研究主题关键词
DISABLE_DEDUP     # 是否关闭去重 True/False
```

---

## 安装依赖

```bash
pip install -r requirements.txt
```

**requirements.txt**:

```
requests
matplotlib
scikit-learn
```

---

## 运行方式

```bash
python paper_bot_github.py
```

* GitHub Actions 可每4小时自动抓取
* 每15天自动生成空提交，保持 schedule 活跃

---

## 输出示例

* 邮件标题：心理学研究雷达（3篇新论文）
* 内容示例：

```
今日研究趋势综述：
1 当前研究热点...
2 常见研究方法...
3 未来方向...

评分：9/10
论文：Cognitive Bias in Decision Making
摘要：
研究问题：
核心发现：
研究方法：
原文链接：https://pubmed.ncbi.nlm.nih.gov/XXXXXX
------------------------
```

* 附件：趋势图 `trend.png`
