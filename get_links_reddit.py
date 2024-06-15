import os
import datetime
import time , random
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.edge import service
from selenium.webdriver.common.keys import Keys
from fake_headers import Headers
from selenium.webdriver.common.action_chains import ActionChains

from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from datetime import date

from webdriver_manager.chrome import ChromeDriverManager

from dotenv import load_dotenv
load_dotenv()

class Timeouts:
    def srt() -> None:
        """short timeout"""
        time.sleep(random.random() + random.randint(0, 2))

    def med() -> None:
        """medium timeout"""
        time.sleep(random.random() + random.randint(2, 5))

    def lng() -> None:
        """long timeout"""
        time.sleep(random.random() + random.randint(5, 10))


reddit_username = os.environ.get('REDDIT_USERNAME')
reddit_password = os.environ.get('REDDIT_PASSWORD')

options = webdriver.ChromeOptions()
options.add_argument('headless')
header = Headers(
    browser="chrome",  # Generate only Chrome UA
    os="win",  # Generate only Windows platform
    headers=False # generate misc headers
)
customUserAgent = header.generate()['User-Agent']

options.add_argument(f"user-agent={customUserAgent}")
# options.add_argument('user-agent="MQQBrowser/26 Mozilla/5.0 (Linux; U; Android 2.3.7; zh-cn; MB200 Build/GRJ22; CyanogenMod-7) AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1"')
options.add_argument("--disable-cache")

options.add_argument('window-size=1920x1080')
# options.add_argument('disable-gpu')

driver = webdriver.Chrome(options= options )

# Function to scroll the page by a specified amount (in pixels)
def scroll_page(by_pixels):
    driver.execute_script(f"window.scrollBy(0, {by_pixels});")

def slow_typing(element, text): 
   for character in text: 
      element.send_keys(character)
      time.sleep(0.05)

def login():
    driver.get("https://www.reddit.com/login/")
    print(reddit_username)
    username_field = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "login-username"))
    )
    password_field =  WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "login-password"))
    )
    slow_typing(username_field, reddit_username)
    slow_typing(password_field, reddit_password)

    
    time.sleep(2)
    

    password_field.send_keys(Keys.ENTER)


    time.sleep(4)

def delete_cache():
    driver.execute_script("window.open('')")  # Create a separate tab than the main one
    driver.switch_to.window(driver.window_handles[-1])  # Switch window to the second tab
    driver.get('chrome://settings/clearBrowserData')  # Open your chrome settings.
    time.sleep(3)
    actions = ActionChains(driver)
    actions.key_down(Keys.SHIFT).send_keys(Keys.TAB * 6).key_up(Keys.SHIFT)  #select "all time" browsing data
    actions.perform()
    time.sleep(3)
    actions.send_keys(Keys.DOWN * 5 +  Keys.TAB * 7 + Keys.ENTER)  #click on "clear data" button
    actions.perform()
    time.sleep(3)
    # driver.close()  
    driver.switch_to.window(driver.window_handles[0])  
    print("Succesfully cleared the browsing data")


def scrape(url, download_path, subreddit):

    # Create the download directory if it doesn't exist
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    output_file = os.path.join(download_path, "links.txt")
    with open(output_file, 'a') as file:
        file.write(f"{subreddit[0]}\n\n")

    try:
        # Send an HTTP GET request to the URL using Selenium
        driver.get(url)
        # Wait for the page to load (adjust the wait time as needed)
        scroll_page("document.body.scrollHeight")
        time.sleep(3)

        wait = WebDriverWait(driver, 5)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[slot="full-post-link"]')))
        # wait.until(EC.presence_of_element_located((By.CLASS_NAME, "SQnoC3ObvgnGjWt90zD9Z")))
        # Get the page source (HTML content) using Selenium
        page_source = driver.page_source

        # Parse the HTML content of the page using BeautifulSoup
        soup = BeautifulSoup(page_source, "html.parser")

        # Find all <div> elements with the specified class
        link_elements = soup.find_all("a", {"slot": "full-post-link"})
        # link_elements = soup.find_all("a", class_="SQnoC3ObvgnGjWt90zD9Z")

        # Iterate through the div elements and filter based on your criteria
        for i in range(min(len(link_elements), 15)):
            link_element = link_elements[i]
            print(f"reddit.com{link_element['href']}")

            with open(output_file, 'a') as file:
                file.write(f"reddit.com{link_element.get('href')}\n")
        with open(output_file, 'a') as file:
            file.write("\n")
    except:
        print(f"No posts today on {subreddit[0]}")
    finally:
        print(f"Finished running {subreddit[0]}")
def run_1():
    print('started 1')
    today = date.today().strftime("%Y-%m-%d")
    # today = "Custom"
    current_date = datetime.datetime.now()

    login()
    time.sleep(2)
    long_form_subreddits = ["nosleep"]
    # considered = [["entitledparents", 1, 6], ["Glitch_in_the_Matrix", 1, 6], ["creepyencounters", 1, 6], ["LetsNotMeet", 1, 6], ["confession", 2, 6],]
    subreddits = [
        ["relationship_advice", 2, 6]
        # , ["relationships", 1, 6],
        # ["confessions", 2, 6], 
        # ["TrueOffMyChest", 1, 6], ["offmychest", 3, 6],
        # ["tifu", 1, 6], ["legaladvice", 1, 6], 
        # ["AmItheAsshole", 3, 6], ["AITAH", 4, 6],  
        # ["askreddit", 4, 6]
    ]

    for subreddit in subreddits:
        # if current_date.weekday() == subreddit[2]:
        if True:
            url = f"https://www.reddit.com/r/{subreddit[0]}/top/?t=week"
            download_path = f"RedditPosts/{today}"
            scrape(url, download_path, subreddit)

    # Close the browser
    delete_cache()
    time.sleep(8)
    driver.quit()
    print('ended 1')

if __name__ == "__main__":
    today = date.today().strftime("%Y-%m-%d")
    # today = "Custom"
    current_date = datetime.datetime.now()

    login()
    time.sleep(2)
    long_form_subreddits = ["nosleep"]
    # considered = [["entitledparents", 1, 6], ["Glitch_in_the_Matrix", 1, 6], ["creepyencounters", 1, 6], ["LetsNotMeet", 1, 6], ["confession", 2, 6],]
    subreddits = [
        ["relationship_advice", 2, 6],
        #   ["relationships", 1, 6],
        # ["confessions", 2, 6], 
        # ["TrueOffMyChest", 1, 6], ["offmychest", 3, 6],
        # ["tifu", 1, 6], ["legaladvice", 1, 6], 
        # ["AmItheAsshole", 3, 6], ["AITAH", 4, 6],  
        # ["askreddit", 4, 6]
    ]

    for subreddit in subreddits:
        # if current_date.weekday() == subreddit[2]:
        if True:
            url = f"https://www.reddit.com/r/{subreddit[0]}/top/?t=week"
            download_path = f"RedditPosts/{today}"
            scrape(url, download_path, subreddit)

    # Close the browser
    delete_cache()
    time.sleep(3)
    driver.quit()