import sys
import asyncio
from playwright.sync_api import sync_playwright
import datetime

# Windows Asyncio Fix (Prevents NotImplementedError)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

BASE_URL = "https://skrmt.spinenx.in"

# Static system defaults
FIXED_CATEGORY = "1"           
FIXED_INOUT_MODE = "B"          
FIXED_IN_TIME = "8:30 AM"       
FIXED_OUT_TIME = "4:30 PM"      
FIXED_REASON = "Daily Attendance"

def run_swipe_for_date(username: str, password: str, punch_date: datetime.date) -> dict:
    formatted_date = punch_date.strftime("%d-%b-%y")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Always start a completely fresh session
        context = browser.new_context()
        page = context.new_page()

        try:
            # 1. Go directly to Login Page
            page.goto(f"{BASE_URL}/login.aspx", wait_until="domcontentloaded")

            # Dismiss cookie consent modal if active
            if page.locator("#dvModal").is_visible():
                page.locator("#btnAccept").click()
                page.wait_for_selector("#dvModal", state="hidden")

            # 2. Fill Credentials & Log In
            page.select_option("#dpCompanyCodeList", "SKRMT")
            page.select_option("#dpConnectAs", "User")
            page.fill("#txtUser", username)
            page.fill("#txtPassword", password)
            
            # Click login and wait for the immediate POST request to finish
            with page.expect_navigation(timeout=30000):
                page.click("#btnLogin")
            
            # 3. Navigate to the Swipe Request List
            page.goto(f"{BASE_URL}/Atten/SwipeRequestList.aspx?mnusr=menu__10201", wait_until="domcontentloaded")

            # 4. Trigger 'Add New' via ASP.NET PostBack
            page.evaluate("__doPostBack('ctl00$BodyContentPlaceHolder$Menu1', 'Add New')")
            page.wait_for_selector("#ctl00_BodyContentPlaceHolder_btnSave", timeout=15000)

            # 5. Fill Fixed Fields
            page.select_option("#ctl00_BodyContentPlaceHolder_drpSwipeCategory", FIXED_CATEGORY)
            page.wait_for_timeout(1000)  # Wait for UpdatePanel partial refresh

            page.fill("#ctl00_BodyContentPlaceHolder_txtFromDate", formatted_date)
            page.press("#ctl00_BodyContentPlaceHolder_txtFromDate", "Tab")
            page.wait_for_timeout(800)

            page.select_option("#ctl00_BodyContentPlaceHolder_dpInout", FIXED_INOUT_MODE)
            
            # Wait for the ASP.NET postback to finish enabling the Out Time field
            page.wait_for_selector("#ctl00_BodyContentPlaceHolder_txtOuttime:not([disabled])", timeout=15000)
            page.wait_for_timeout(500)

            # Force the time values using JavaScript to bypass the ASP.NET MaskedEdit Extender
            page.evaluate(f"document.getElementById('ctl00_BodyContentPlaceHolder_txtInTime').value = '{FIXED_IN_TIME}';")
            page.evaluate(f"document.getElementById('ctl00_BodyContentPlaceHolder_txtOuttime').value = '{FIXED_OUT_TIME}';")
            page.evaluate(f"document.getElementById('ctl00_BodyContentPlaceHolder_txtReason').value = '{FIXED_REASON}';")

            # 6. Submit Form
            page.click("#ctl00_BodyContentPlaceHolder_btnSave")

            # CRITICAL FIX: Wait for the Save button to disappear instead of watching the URL
            page.wait_for_selector("#ctl00_BodyContentPlaceHolder_btnSave", state="hidden", timeout=30000)
            
            # Use 'tbody tr' to handle jQuery DataTables rendering
            row_locator = page.locator("#ctl00_BodyContentPlaceHolder_GridView1 tbody tr").first
            row_locator.wait_for(state="visible", timeout=30000)
            
            latest_row = row_locator.inner_text().replace("\n", " | ")
            
            browser.close()
            return {"status": "success", "date": formatted_date, "details": latest_row}

        except Exception as e:
            browser.close()
            return {"status": "error", "date": formatted_date, "message": str(e)}
