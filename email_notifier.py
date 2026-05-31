import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import requests

from config import FAMILY_RECIPIENT_EMAILS, RDA, STAPLES_LIST_ID, APP_URL
from mealie_client import MealieClient
from recipe_nutrition import calculate_nutrition_for_range
from recipe_crawler import check_blackstone_compatibility

def send_email(subject, html_content):
    """Send an email using SMTP settings."""
    smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASSWORD')
    from_email = os.getenv('SMTP_FROM_EMAIL')
    from_name = os.getenv('SMTP_FROM_NAME', 'Mealie Planner')

    if not smtp_user or not smtp_pass:
        print("SMTP settings are missing. Cannot send email.")
        return False

    # Fetch recipients dynamically from all registered Mealie users
    recipients = []
    try:
        client = MealieClient()
        users = client.get_users()
        recipients = [u.get('email') for u in users if u.get('email')]
        if recipients:
            print(f"[Email] Dynamically loaded recipients from Mealie: {recipients}")
    except Exception as e:
        print(f"[Email] Could not fetch Mealie users, falling back to static list: {e}")
        recipients = FAMILY_RECIPIENT_EMAILS

    if not recipients:
        print("No recipient emails found. Cannot send email.")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{from_name} <{from_email}>"
    msg['To'] = ", ".join(recipients)

    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, recipients, msg.as_string())
        print(f"Successfully sent email: '{subject}' to {recipients}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def send_saturday_report_email(start_date_str, end_date_str, exclude_text, freezer_items, low_staples_ids, special_requests=""):
    """Send summary of generated meal plan, staples, and weekly average nutrients."""
    try:
        print(f"[Email] Generating Saturday report email for {start_date_str}...")
        client = MealieClient()
        meal_plans = client.get_meal_plan(start_date_str, end_date_str)
        daily_nutrients, averages = calculate_nutrition_for_range(start_date_str, end_date_str)
        
        # Resolve low staples names
        staples = client.get_shopping_list_items(STAPLES_LIST_ID)
        staple_id_map = {item['id'].replace('-', ''): item['note'] for item in staples}
        low_staples_names = []
        for s_id in low_staples_ids:
            note = staple_id_map.get(s_id.replace('-', ''))
            if note:
                low_staples_names.append(note)

        # Build scheduled meals rows
        meal_rows = ""
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        for i in range(7):
            curr = start_date + timedelta(days=i)
            d_str = curr.strftime("%Y-%m-%d")
            day_name = curr.strftime("%A")
            
            bf = next((p['title'] for p in meal_plans if p['date'] == d_str and p['entryType'] == 'breakfast'), "Staples")
            ln = next((p['title'] for p in meal_plans if p['date'] == d_str and p['entryType'] == 'lunch'), "Leftovers")
            
            # Dinner recipe name
            dinner_item = next((p for p in meal_plans if p['date'] == d_str and p['entryType'] == 'dinner'), None)
            dn = "Eating Out"
            if dinner_item:
                if dinner_item.get('recipeId'):
                    try:
                        r = client.get_recipe_details(dinner_item['recipeId'])
                        dn = f'<a href="https://mealie.cosmoslab.dev/g/home/r/{r["slug"]}" style="color: #E58325; text-decoration: none; border-bottom: 1px dotted #E58325;">{r["name"]}</a>'
                    except:
                        dn = "Recipe Details Unavailable"
                elif dinner_item.get('title'):
                    dn = dinner_item['title']
                    
            meal_rows += f"""
            <tr style="border-bottom: 1px solid #eee;">
              <td style="padding: 10px; font-weight: bold; width: 120px;">{day_name}</td>
              <td style="padding: 10px; color: #555;">{bf}</td>
              <td style="padding: 10px; color: #555;">{ln}</td>
              <td style="padding: 10px; color: #E58325; font-weight: bold;">{dn}</td>
            </tr>
            """

        # Build nutrition table rows
        nut_rows = ""
        for k, rda_val in RDA.items():
            avg_val = averages.get(k, 0.0)
            pct = round((avg_val / rda_val) * 100) if rda_val > 0 else 0
            status_color = "#43A047"
            if k == "sodium" and pct > 100:
                status_color = "#EF5350"
            elif k == "fiber" and pct < 100:
                status_color = "#E58325"
                
            unit = "g"
            if k == "calories": unit = "kcal"
            elif k in ["sodium", "cholesterol"]: unit = "mg"
            
            nut_rows += f"""
            <tr style="border-bottom: 1px solid #eee;">
              <td style="padding: 10px; text-transform: capitalize;">{k}</td>
              <td style="padding: 10px; font-weight: bold;">{avg_val} {unit}</td>
              <td style="padding: 10px; color: #777;">{rda_val} {unit}</td>
              <td style="padding: 10px; font-weight: bold; color: {status_color};">{pct}%</td>
            </tr>
            """

        # --- TODAY'S HIGHLIGHTS (Combined Daily Email for Saturday) ---
        today_highlights = ""
        try:
            today_nutrients = daily_nutrients.get(start_date_str, {})
            highlights_nut_text = ""
            for k, v in today_nutrients.items():
                unit = "g"
                if k == "calories": unit = "kcal"
                elif k in ["sodium", "cholesterol"]: unit = "mg"
                target = RDA.get(k, 0.0)
                pct = round((v / target) * 100) if target > 0 else 0
                color = "#43A047"
                if k == "sodium" and pct > 100: color = "#EF5350"
                elif k == "fiber" and pct < 100: color = "#E58325"
                highlights_nut_text += f"<span style='display:inline-block; margin-right: 15px; background: #f1f3f5; padding: 5px 10px; border-radius: 4px; font-size:12px; margin-bottom: 5px;'><strong>{k.capitalize()}</strong>: {v} {unit} (<span style='color:{color}; font-weight:bold;'>{pct}%</span>)</span>"

            # Get Saturday's menu for highlights
            sat_bf = next((p['title'] for p in meal_plans if p['date'] == start_date_str and p['entryType'] == 'breakfast'), "Staples")
            sat_ln = next((p['title'] for p in meal_plans if p['date'] == start_date_str and p['entryType'] == 'lunch'), "Leftovers")
            sat_dn_item = next((p for p in meal_plans if p['date'] == start_date_str and p['entryType'] == 'dinner'), None)
            sat_dn_title = "Eating Out"
            sat_recipe = None
            if sat_dn_item:
                if sat_dn_item.get('recipeId'):
                    try:
                        sat_recipe = client.get_recipe_details(sat_dn_item['recipeId'])
                        sat_dn_title = f'<a href="https://mealie.cosmoslab.dev/g/home/r/{sat_recipe["slug"]}" style="color: #E58325; text-decoration: none; border-bottom: 1px dotted #E58325;">{sat_recipe["name"]}</a>'
                    except:
                        sat_dn_title = "Recipe Details Unavailable"
                elif sat_dn_item.get('title'):
                    sat_dn_title = sat_dn_item['title']

            # Dinner prep check (incorporating AI prep note from Mealie if available)
            today_prep_tip = ""
            ai_prep_note = sat_dn_item.get('text') or "" if sat_dn_item else ""
            if ai_prep_note:
                today_prep_tip = f"""
                <div style="background-color: #fff9db; border-left: 4px solid #fcc419; padding: 15px; border-radius: 4px; margin: 15px 0; font-size: 14px; color: #5c3e03;">
                  📝 <strong>Dinner Prep Instructions:</strong> {ai_prep_note}
                </div>
                """
            elif sat_recipe and check_blackstone_compatibility(sat_recipe):
                today_prep_tip = """
                <div style="background-color: #fff9db; border-left: 4px solid #fcc419; padding: 15px; border-radius: 4px; margin: 15px 0; font-size: 14px; color: #5c3e03;">
                  🍳 <strong>Blackstone Griddle Fired Up!</strong> Tonight's dinner is griddle-ready. Consider batch-cooking proteins or veggies for the coming days while it's hot!
                </div>
                """

            today_highlights = f"""
            <div style="background-color: #fff4e6; border: 1px solid #ffd8a8; border-radius: 8px; padding: 20px; margin-bottom: 30px;">
              <h3 style="color: #d9480f; margin-top: 0; border-bottom: 1px solid #ffd8a8; padding-bottom: 10px;">🍽️ Saturday's Daily Briefing</h3>
              
              <div style="margin: 15px 0;">
                <p style="font-size: 15px; margin: 5px 0;">☕ <strong>Breakfast:</strong> <span style="color:#555;">{sat_bf}</span></p>
                <p style="font-size: 15px; margin: 5px 0;">🥗 <strong>Lunch:</strong> <span style="color:#555;">{sat_ln}</span></p>
                <p style="font-size: 16px; font-weight: bold; color: #E58325; margin: 10px 0;">🥘 Dinner: {sat_dn_title}</p>
              </div>

              {today_prep_tip}
              
              <div style="line-height: 1.6; border-top: 1px solid #ffd8a8; padding-top: 10px; margin-top: 10px;">
                <p style="font-size: 13px; font-weight: bold; margin-bottom: 8px; color: #d9480f;">Today's Nutritional Totals:</p>
                {highlights_nut_text}
              </div>
            </div>
            """
        except Exception as e:
            print(f"Error generating Saturday highlights: {e}")

        # Clean up freezer & special requests text
        freezer_str = freezer_items if freezer_items else "None specified"
        special_requests_str = special_requests if special_requests else "None"
        staples_str = f"<br/>* <strong>Low Staples Added</strong>: {', '.join(low_staples_names)}" if low_staples_names else ""
        exclude_text_str = exclude_text if exclude_text else "None"
     
        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #f7f9fc; padding: 20px; color: #333;">
            <div style="max-width: 650px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #e1e8ed;">
              <h2 style="color: #43A047; margin-top: 0; text-align: center;">🛒 Weekly Meal Plan & Shopping List Ready!</h2>
              <p style="font-size: 16px; line-height: 1.6;">Hi Nathan & Kristin,</p>
              <p style="font-size: 16px; line-height: 1.6;">Your meal plan has been generated for the week of <strong>{start_date_str} to {end_date_str}</strong>. Mealie's active shopping list has been populated with ingredients.</p>

              {today_highlights}

              <h3 style="color: #2F3E46; border-bottom: 2px solid #eee; padding-bottom: 5px;">📅 Weekly Calendar</h3>
              <table style="width: 100%; border-collapse: collapse;">
                <thead>
                  <tr style="background-color: #f7f9fc; text-align: left; border-bottom: 2px solid #ddd;">
                    <th style="padding: 10px;">Day</th>
                    <th style="padding: 10px;">Breakfast</th>
                    <th style="padding: 10px;">Lunch</th>
                    <th style="padding: 10px;">Dinner</th>
                  </tr>
                </thead>
                <tbody>
                  {meal_rows}
                </tbody>
              </table>
     
              <h3 style="color: #2F3E46; border-bottom: 2px solid #eee; padding-bottom: 5px; margin-top: 30px;">🥦 Weekly Nutritional Analysis (Family Average)</h3>
              <p style="font-size: 14px; color: #666; margin-top: 0;">Calculated daily average per person, including estimated breakfast staples & leftovers.</p>
              <table style="width: 100%; border-collapse: collapse;">
                <thead>
                  <tr style="background-color: #f7f9fc; text-align: left; border-bottom: 2px solid #ddd;">
                    <th style="padding: 10px;">Nutrient</th>
                    <th style="padding: 10px;">Daily Avg</th>
                    <th style="padding: 10px;">RDA Target</th>
                    <th style="padding: 10px;">% Target</th>
                  </tr>
                </thead>
                <tbody>
                  {nut_rows}
                </tbody>
              </table>
     
              <div style="background-color: #e8f5e9; border-left: 4px solid #43A047; padding: 15px; border-radius: 4px; margin-top: 30px; font-size: 14px;">
                <strong>📝 Submission Context:</strong><br/>
                * <strong>Meal Opt-Outs</strong>: {exclude_text_str}<br/>
                * <strong>Freezer/Pantry/Fridge Items</strong>: {freezer_str}{staples_str}<br/>
                * <strong>Special Requests</strong>: {special_requests_str}
              </div>
     
              <p style="font-size: 14px; color: #888; text-align: center; margin-top: 30px;">
                Need to change something? Go to <a href="{APP_URL}" style="color: #E58325;">Your Dashboard</a> to edit dates, swap dinners, and sync your list instantly.
              </p>
            </div>
          </body>
        </html>
        """
        send_email(f"🛒 Mealie Shopping List & Plan Ready ({start_date_str})", html)
    except Exception as e:
        print(f"[Email] Failed to generate or send Saturday report email: {e}")
        import traceback
        traceback.print_exc()
