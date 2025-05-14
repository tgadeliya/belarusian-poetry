import os
import re
import scrapy
from scrapy.crawler import CrawlerProcess
from parsel import Selector


# Configuration
BASE_URL = 'https://knihi.com'
START_URL = BASE_URL + '/autary.html'
TARGET_SECTIONS = {'Вершы', 'Паэмы'}
OUTPUT_DIR = 'poems'
DOWNLOAD_DELAY = 1.0        

class PoetrySpider(scrapy.Spider):
    name = 'knihi_poetry'
    start_urls = [START_URL]
    custom_settings = {
        'DOWNLOAD_DELAY': DOWNLOAD_DELAY,
        'LOG_LEVEL': 'INFO',
    }

    def parse(self, response):
        # Iterate over author directory links: href starts and ends with '/'
        for author_sel in response.css("a[href^='/' ][href$='/']"):
            author_name = author_sel.xpath('normalize-space(text())').get()
            href = author_sel.attrib.get('href')
            if not author_name or not href:
                continue

            author_name = author_name.strip()
            author_url = response.urljoin(href)
            self.logger.info(f"Processing: {author_name}  {author_url}")

            # Request author page, pass author_name
            yield scrapy.Request(
                url=author_url,
                callback=self.parse_author,
                cb_kwargs={'author_name': author_name}
            )

    def parse_author(self, response, author_name):
        # Look for sections marked by <div class="titler-section">Section Name</div>
        for section in response.css('div.titler-section'):
            section_title = section.xpath('normalize-space(text())').get()
            if section_title in TARGET_SECTIONS:
                self.logger.info(f"  Found section '{section_title}' for {author_name}")
                # The poem links are typically in the next <ul> after this div
                ul = section.xpath('following-sibling::*[1][self::ul]')
                for li in ul.xpath('.//li'):
                    # Within each <li>, skip epub links and find the .html link
                    for link in li.xpath('.//a'):
                        href = link.attrib.get('href', '')
                        if href.endswith('.html'):
                            poem_title = link.xpath('normalize-space(text())').get()
                            poem_url = response.urljoin(href)
                            yield scrapy.Request(
                                url=poem_url,
                                callback=self.parse_poem,
                                cb_kwargs={
                                    'author_name': author_name,
                                    'poem_title': poem_title,
                                }
                            )

    def parse_poem(self, response, author_name, poem_title):
        # Determine poem title from page: second <h2> without <a>
        page_title = response.xpath("//h2[not(a)][1]/text()").get()
        title = page_title.strip() if page_title else poem_title

        # Extract poem body between BOOK_BEGIN and BOOK_END comments
        body = response.text
        match = re.search(r"<!--\s*BOOK_BEGIN\s*-->(.*?)<!--\s*BOOK_END\s*-->", body, re.S)
        if match:
            raw_html = match.group(1)
            sel = Selector(text=raw_html)
            paragraphs = sel.xpath('//p/text()').getall()
            lines = [p.strip() for p in paragraphs if p.strip() and p.strip() != '\xa0']
            poem_text = '\n'.join(lines)
        else:
            poem_text = response.xpath("string(//div[@id='content'] | //body)").get().strip()

        # Save to file
        author_dir = os.path.join(OUTPUT_DIR, author_name)
        os.makedirs(author_dir, exist_ok=True)
        slug = os.path.basename(response.url).rstrip('.html')
        filename = f"{slug}.txt"
        file_path = os.path.join(author_dir, filename)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(poem_text)
        self.logger.info(f"    Saved poem '{title}' to {file_path}")

if __name__ == '__main__':
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    process = CrawlerProcess()
    process.crawl(PoetrySpider)
    process.start()  # the script will block here until the crawl is finished
