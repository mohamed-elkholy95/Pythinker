import requests
from bs4 import BeautifulSoup
from collections import Counter
import re


def get_html_content(url):
    """Fetches HTML content from a given URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        return f"Error fetching URL: {e}"


def extract_keywords(text, num_keywords=10):
    """Extracts top keywords from text."""
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    word_counts = Counter(words)
    return word_counts.most_common(num_keywords)


def analyze_content(html_content):
    """Analyzes content for SEO elements."""
    soup = BeautifulSoup(html_content, "html.parser")

    title = soup.title.string if soup.title else "N/A"
    meta_description = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_description["content"] if meta_description else "N/A"
    h1_tags = [h1.get_text() for h1 in soup.find_all("h1")]
    h2_tags = [h2.get_text() for h2 in soup.find_all("h2")]
    all_text = soup.get_text()
    word_count = len(all_text.split())

    return {
        "title": title,
        "meta_description": meta_description,
        "h1_tags": h1_tags,
        "h2_tags": h2_tags,
        "word_count": word_count,
        "keywords": extract_keywords(all_text),
    }


def calculate_readability(text):
    """Calculates a simple readability score (e.g., Flesch-Kincaid-like)."""
    sentences = re.split(r"[.!?]", text)
    sentences = [s for s in sentences if s.strip()]
    num_sentences = len(sentences)

    words = re.findall(r"\b\w+\b", text)
    num_words = len(words)

    syllables = sum(count_syllables(word) for word in words)

    if num_words == 0 or num_sentences == 0:
        return 0.0

    # Simplified Flesch-Kincaid formula
    score = (
        206.835 - 1.015 * (num_words / num_sentences) - 84.6 * (syllables / num_words)
    )
    return max(0.0, score)  # Score cannot be negative


def count_syllables(word):
    """Counts syllables in a word (simplified)."""
    word = word.lower()
    count = 0
    vowels = "aeiouy"
    if word[0] in vowels:
        count += 1
    for index in range(1, len(word)):
        if word[index] in vowels and word[index - 1] not in vowels:
            count += 1
    if word.endswith("e"):
        count -= 1
    if count == 0:
        count += 1
    return count


def generate_seo_report(url, analysis_results, readability_score):
    """Generates a Markdown formatted SEO report."""
    report = f"# SEO Analysis Report for: {url}\n\n"
    report += "## On-Page Elements\n"
    report += f"- **Title:** {analysis_results['title']}\n"
    report += f"- **Meta Description:** {analysis_results['meta_description']}\n"
    report += f"- **H1 Tags:** {', '.join(analysis_results['h1_tags']) or 'None'}\n"
    report += f"- **H2 Tags:** {', '.join(analysis_results['h2_tags']) or 'None'}\n"
    report += f"- **Word Count:** {analysis_results['word_count']}\n\n"

    report += "## Top Keywords\n"
    for keyword, count in analysis_results["keywords"]:
        report += f"- {keyword}: {count}\n"
    report += "\n"

    report += "## Readability\n"
    report += f"- **Readability Score:** {readability_score:.2f} (Higher is easier to read)\n\n"

    return report


if __name__ == "__main__":
    target_url = input("Enter the URL to analyze: ")
    html_content = get_html_content(target_url)

    if "Error" in html_content:
        print(html_content)
    else:
        analysis = analyze_content(html_content)
        readability = calculate_readability(
            BeautifulSoup(html_content, "html.parser").get_text()
        )
        report_content = generate_seo_report(target_url, analysis, readability)

        with open("seo_report.md", "w") as f:
            f.write(report_content)
        print("SEO report generated successfully: seo_report.md")
