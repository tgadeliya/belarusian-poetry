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
        for section in response.xpath('//div[contains(@class,"titler-section")]'):
            # Skip any ‘Вершы’ (or other section) that follows a titler-lang block
            container = section.xpath('ancestor::div[contains(@class,"container")][1]')
            if container.xpath('preceding-sibling::div[contains(@class,"titler-lang")]'):
                continue

            section_title = section.xpath('normalize-space(text())').get()
            if section_title in TARGET_SECTIONS:
                self.logger.info(f"  Found section '{section_title}' for {author_name}")
                # The poem links are typically in the next <ul> after this div
                ul = section.xpath('following-sibling::*[1][self::ul]')
                for li in ul.xpath('.//li'):
                    # Within each <li>, skip html links and find the .epub link
                    for link in li.xpath('.//a'):
                        href = link.attrib.get('href', '')
                        if href.endswith('.epub'):
                            poem_title = link.xpath('normalize-space(text())').get()
                            poem_epub_url = response.urljoin(href)
                            yield scrapy.Request(
                                url=poem_epub_url,
                                callback=self.parse_epub_poem,
                                cb_kwargs={
                                    'epub_url': poem_epub_url,
                                    'author_name': author_name,
                                    'poem_title': poem_title,
                                    'section': section_title,
                                }
                            )
    
    def parse_epub_poem(self, response, epub_url, author_name, poem_title, section):
        # Extract filename from URL
        filename = epub_url.rsplit('/', 1)[-1]
        # Build output directory: poems/<AuthorName>/epubs/
        author_dir = os.path.join(OUTPUT_DIR, author_name, section)
        os.makedirs(author_dir, exist_ok=True)
        file_path = os.path.join(author_dir, filename)

        # Write out the binary .epub content
        with open(file_path, 'wb') as f:
            f.write(response.body)

        self.logger.info(f"    Downloaded EPUB “{poem_title}” to {file_path}")



if __name__ == '__main__':
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    process = CrawlerProcess()
    process.crawl(PoetrySpider)
    process.start()  # the script will block here until the crawl is finished
