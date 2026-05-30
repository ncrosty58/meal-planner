import os
import sys
import queue
import threading
import json
from flask import Flask, render_template, request, redirect, url_for, flash, Response
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from meal_planner import (
    MealieClient,
    generate_weekly_plan,
    sync_shopping_list,
    calculate_nutrition_for_range,
    check_blackstone_compatibility,
    send_email
)

from config import ACTIVE_LIST_ID, STAPLES_LIST_ID, RDA, TIMEZONE, APP_URL, FAMILY_RECIPIENT_EMAILS, FAMILY_NAMES
from clear_mealie import wipe_mealie_data

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'mealie_companion_secret_9926')

# Helper to calculate the planning week range (starts Saturday, ends next Friday)
def get_planning_dates():
    today = datetime.now(pytz.timezone(TIMEZONE))
    days_to_saturday = (5 - today.weekday() + 7) % 7
    start_date = today + timedelta(days=days_to_saturday)
    end_date = start_date + timedelta(days=6)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")



@app.template_filter('select_day_name')
def select_day_name(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%A")
    except Exception as e:
        print(f"Error parsing day name filter: {e}")
        return ""



# Shared variable to hold manually selected low staples IDs for the current week's sync
current_week_low_staples = []

@app.route('/')
def index():
    success_msg = request.args.get('success_msg')
    error_msg = request.args.get('error_msg')
    if success_msg:
        flash(success_msg, "success")
    if error_msg:
        flash(error_msg, "danger")
        
    try:
        client = MealieClient()
    except Exception as e:
        return f"<h1>Configuration Error</h1><p>{str(e)}</p>"

    # 1. Determine if a meal plan is already active for the upcoming/current week
    start_date_str, end_date_str = get_planning_dates()
    meal_plans = client.get_meal_plan(start_date_str, end_date_str)
    
    # Check if there are scheduled dinner recipes in the database
    dinners = [p for p in meal_plans if p['entryType'] == 'dinner' and (p.get('recipeId') or p.get('title') == 'Eating Out')]
    
    # 2. Get staples list items for the form (or dashboard)
    staples = []
    try:
        staples = client.get_shopping_list_items(STAPLES_LIST_ID)
    except Exception as e:
        print(f"Error reading staples list: {e}")

    all_recipes = []
    try:
        all_recipes = client.get_all_recipes()
    except Exception as e:
        print(f"Error reading recipes: {e}")

    if dinners:
        # PLAN IS ALREADY SUBMITTED & GENERATED FOR THIS WEEK!
        # Render the ACTIVE WEEK DASHBOARD
        daily_nutrition, averages = calculate_nutrition_for_range(start_date_str, end_date_str)
        
        # Pull shopping list items
        shopping_list = []
        try:
            shopping_list = client.get_shopping_list_items(ACTIVE_LIST_ID)
        except Exception as e:
            print(f"Error reading active shopping list: {e}")

        # Blackstone Griddle suggestions
        blackstone_tips = []
        scheduled_recipes = []
        for p in meal_plans:
            if p['entryType'] == 'dinner' and p.get('recipeId'):
                try:
                    r_details = client.get_recipe_details(p['recipeId'])
                    scheduled_recipes.append(r_details)
                except:
                    pass
                    
        # Look for Blackstone griddle combos
        has_blackstone = any(check_blackstone_compatibility(r) for r in scheduled_recipes)
        if has_blackstone:
            blackstone_tips.append("🍳 <strong>Blackstone Griddle Fired Up!</strong> You have griddle meals scheduled. Plan to batch-cook veggies or proteins for the upcoming days to save heating time!")
            
        return render_template(
            'index.html',
            is_submitted=True,
            start_date=start_date_str,
            end_date=end_date_str,
            meal_plans=meal_plans,
            shopping_list=shopping_list,
            daily_nutrition=daily_nutrition,
            averages=averages,
            rda=RDA,
            blackstone_tips=blackstone_tips,
            all_recipes=all_recipes,
            staples=staples,
            low_staples=current_week_low_staples
        )
    else:
        # NO PLAN YET. Render the QUESTIONNAIRE FORM
        return render_template(
            'index.html',
            is_submitted=False,
            start_date=start_date_str,
            end_date=end_date_str,
            staples=staples,
            low_staples=current_week_low_staples
        )


@app.route('/plan-stream')
def plan_stream():
    exclude_text = request.args.get('exclude_text', '')
    freezer_items = request.args.get('freezer_items', '')
    special_requests = request.args.get('special_requests', '')
    low_staples_ids = request.args.getlist('low_staples')
    
    q = queue.Queue()
    start_date_str, end_date_str = get_planning_dates()
    
    global current_week_low_staples
    current_week_low_staples = low_staples_ids
    
    def worker():
        try:
            def callback(msg, pct):
                q.put({"type": "progress", "message": msg, "progress": pct})
                
            generate_weekly_plan(
                start_date_str=start_date_str,
                end_date_str=end_date_str,
                exclude_text=exclude_text,
                freezer_items=freezer_items,
                special_requests=special_requests,
                low_staples_ids=low_staples_ids,
                progress_callback=callback
            )
            
            # Send Saturday report email
            callback("Sending weekly plan report email to family...", 99)
            send_saturday_report_email(start_date_str, end_date_str, exclude_text, freezer_items, low_staples_ids, special_requests)
            
            q.put({"type": "complete"})
        except Exception as e:
            q.put({"type": "error", "message": str(e)})
            
    threading.Thread(target=worker).start()
    
    def generate():
        while True:
            try:
                item = q.get(timeout=180) # 3 mins timeout
                if item["type"] == "complete":
                    yield f"data: {json.dumps({'status': 'complete', 'progress': 100})}\n\n"
                    break
                elif item["type"] == "error":
                    yield f"data: {json.dumps({'status': 'error', 'message': item['message']})}\n\n"
                    break
                elif item["type"] == "progress":
                    yield f"data: {json.dumps({'status': item['message'], 'progress': item['progress']})}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Plan generation timed out.'})}\n\n"
                break
                
    return Response(generate(), mimetype='text/event-stream')


@app.route('/plan', methods=['POST'])
def plan():
    exclude_text = request.form.get('exclude_text', '')
    freezer_items = request.form.get('freezer_items', '')
    special_requests = request.form.get('special_requests', '')
    low_staples_ids = request.form.getlist('low_staples')
    
    global current_week_low_staples
    current_week_low_staples = low_staples_ids
    
    start_date_str, end_date_str = get_planning_dates()
    
    try:
        generate_weekly_plan(
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            exclude_text=exclude_text,
            freezer_items=freezer_items,
            special_requests=special_requests,
            low_staples_ids=low_staples_ids
        )
        
        # Send out the Saturday report email
        send_saturday_report_email(start_date_str, end_date_str, exclude_text, freezer_items, low_staples_ids, special_requests)
        flash("Successfully generated weekly plan and updated active shopping list!", "success")
    except Exception as e:
        flash(f"Error generating plan: {str(e)}", "danger")
        
    return redirect(url_for('index'))


@app.route('/sync', methods=['POST'])
def sync():
    start_date_str, end_date_str = get_planning_dates()
    global current_week_low_staples
    
    # Update low staples from POST form parameter if available
    low_staples_ids = request.form.getlist('low_staples')
    if low_staples_ids or request.form.get('staples_submitted') == '1':
        current_week_low_staples = low_staples_ids
        
    try:
        sync_shopping_list(start_date_str, end_date_str, current_week_low_staples)
        flash("Recalculated active shopping list successfully!", "success")
    except Exception as e:
        flash(f"Error syncing shopping list: {str(e)}", "danger")
        
    return redirect(url_for('index'))


@app.route('/clear', methods=['POST'])
def clear_plan_route():
    try:
        wipe_mealie_data()
        flash("Successfully cleared meal plans and active shopping list from Mealie!", "success")
    except Exception as e:
        flash(f"Error clearing Mealie data: {str(e)}", "danger")
    return redirect(url_for('index'))


@app.route('/change-meal', methods=['POST'])
def change_meal():
    date_str = request.form.get('date')
    recipe_id = request.form.get('recipe_id')
    meal_plan_entry_id = request.form.get('entry_id')
    
    client = MealieClient()
    start_date_str, end_date_str = get_planning_dates()
    global current_week_low_staples
    
    try:
        if meal_plan_entry_id:
            # Delete old entry
            client.delete_meal_plan_entry(meal_plan_entry_id)
            
        # Schedule new meal
        client.schedule_meal(date_str, "dinner", recipe_id=recipe_id)
        
        # Trigger shopping list sync immediately
        sync_shopping_list(start_date_str, end_date_str, current_week_low_staples)
        flash("Dinner recipe updated and shopping list recalculated!", "success")
    except Exception as e:
        flash(f"Error changing meal: {str(e)}", "danger")
        
    return redirect(url_for('index'))


@app.route('/trigger-qa')
def trigger_qa():
    """Manual trigger endpoint for Saturday Q/A email."""
    if send_saturday_qa_email_job():
        return "Q/A Email sent successfully!"
    return "Failed to send Q/A email.", 500


@app.route('/trigger-daily')
def trigger_daily():
    """Manual trigger endpoint for daily reminder email."""
    if send_daily_reminder_job():
        return "Daily reminder sent successfully!"
    return "Failed to send daily reminder.", 500


# --- Background Job Implementations ---

def send_saturday_qa_email_job():
    """Job to email Saturday Questionnaire link to family."""
    app_url = APP_URL
    
    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #f7f9fc; padding: 20px; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #e1e8ed;">
          <h2 style="color: #E58325; margin-top: 0; text-align: center;">📋 Weekly Meal Planning Questionnaire</h2>
          <p style="font-size: 16px; line-height: 1.6;">Hi {FAMILY_NAMES},</p>
          <p style="font-size: 16px; line-height: 1.6;">It is Saturday, which means it is time to plan meals and shop for the upcoming week!</p>
          <p style="font-size: 16px; line-height: 1.6;">Please click the button below to fill out the questionnaire (choose eating-out days, freezer items, and check off running-low staples):</p>
          
          <div style="text-align: center; margin: 30px 0;">
            <a href="{app_url}" style="background-color: #E58325; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; display: inline-block;">Fill Out Questionnaire</a>
          </div>
          
          <p style="font-size: 14px; color: #888; text-align: center;">Note: Link redirects to your active dashboard once submitted to prevent double-entries.</p>
        </div>
      </body>
    </html>
    """
    return send_email("📋 Weekly Meal Planning Questionnaire", html)


def send_saturday_report_email(start_date_str, end_date_str, exclude_text, freezer_items, low_staples_ids, special_requests=""):
    """Send summary of generated meal plan, staples, and weekly average nutrients."""
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
                    dn = r['name']
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

    # Clean up freezer & special requests text
    freezer_str = freezer_items if freezer_items else "None specified"
    special_requests_str = special_requests if special_requests else "None"
    staples_str = ", ".join(low_staples_names) if low_staples_names else "None running low"
    exclude_text_str = exclude_text if exclude_text else "None"
 
    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #f7f9fc; padding: 20px; color: #333;">
        <div style="max-width: 650px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #e1e8ed;">
          <h2 style="color: #43A047; margin-top: 0; text-align: center;">🛒 Weekly Meal Plan & Shopping List Ready!</h2>
          <p style="font-size: 16px; line-height: 1.6;">Hi Nathan & Kristin,</p>
          <p style="font-size: 16px; line-height: 1.6;">Your meal plan has been generated for the week of <strong>{start_date_str} to {end_date_str}</strong>. Mealie's active shopping list has been populated with ingredients.</p>
          
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
            * <strong>Low Staples Added</strong>: {staples_str}<br/>
            * <strong>Freezer Items Checked</strong>: {freezer_str}<br/>
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


def send_daily_reminder_job():
    """Job to email daily meal reminders to family at 7:00 AM."""
    client = MealieClient()
    today_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
    
    # Fetch meal plans for today
    plans = client.get_meal_plan(today_str, today_str)
    if not plans:
        print("No scheduled meals for today.")
        return False
        
    bf = next((p['title'] for p in plans if p['entryType'] == 'breakfast'), "Staples")
    ln = next((p['title'] for p in plans if p['entryType'] == 'lunch'), "Leftovers")
    
    dinner_item = next((p for p in plans if p['entryType'] == 'dinner'), None)
    dn_title = "Eating Out"
    dn_recipe = None
    if dinner_item:
        if dinner_item.get('recipeId'):
            try:
                dn_recipe = client.get_recipe_details(dinner_item['recipeId'])
                dn_title = dn_recipe['name']
            except:
                dn_title = "Recipe Details Unavailable"
        elif dinner_item.get('title'):
            dn_title = dinner_item['title']

    # Nutrition for today
    daily_nutrition, _ = calculate_nutrition_for_range(today_str, today_str)
    today_nutrients = daily_nutrition.get(today_str, {})
    
    # Assemble nutrition list
    nut_text = ""
    for k, v in today_nutrients.items():
        unit = "g"
        if k == "calories": unit = "kcal"
        elif k in ["sodium", "cholesterol"]: unit = "mg"
        
        target = RDA.get(k, 0.0)
        pct = round((v / target) * 100) if target > 0 else 0
        color = "#43A047"
        if k == "sodium" and pct > 100: color = "#EF5350"
        elif k == "fiber" and pct < 100: color = "#E58325"
        
        nut_text += f"<span style='display:inline-block; margin-right: 15px; background: #f1f3f5; padding: 5px 10px; border-radius: 4px; font-size:13px;'><strong>{k.capitalize()}</strong>: {v} {unit} (<span style='color:{color}; font-weight:bold;'>{pct}%</span>)</span>"

    # Griddle prep check
    prep_tip = ""
    if dn_recipe and check_blackstone_compatibility(dn_recipe):
        prep_tip = """
        <div style="background-color: #fff9db; border-left: 4px solid #fcc419; padding: 15px; border-radius: 4px; margin: 20px 0; font-size: 14px; color: #5c3e03;">
          <strong>🍳 Blackstone Griddle Alert:</strong> Tonight's dinner uses the Blackstone! Remember to check Mealie for the next few days to see if you can double-cook proteins or veggies right now.
        </div>
        """

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #f7f9fc; padding: 20px; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #e1e8ed;">
          <h2 style="color: #E58325; margin-top: 0; text-align: center;">🍽️ Today's Family Meal Plan</h2>
          <p style="font-size: 16px; text-align: center; color: #666; margin-top: -10px;">{datetime.now().strftime("%A, %B %d, %Y")}</p>
          
          <div style="margin-top: 25px; border-top: 1px solid #eee; padding-top: 15px;">
            <p style="font-size: 16px;">☕ <strong>Breakfast:</strong> <span style="color:#555;">{bf}</span></p>
            <p style="font-size: 16px;">🥗 <strong>Lunch:</strong> <span style="color:#555;">{ln}</span></p>
            <p style="font-size: 18px; font-weight: bold; color: #E58325; margin: 20px 0;">🥘 Dinner: {dn_title}</p>
          </div>
          
          {prep_tip}
          
          <h4 style="color: #2F3E46; margin-bottom: 10px; margin-top:30px; border-bottom:1px solid #eee; padding-bottom:5px;">📊 Today's Nutritional Summary (Individual portions)</h4>
          <div style="line-height: 1.8;">
            {nut_text}
          </div>
        </div>
      </body>
    </html>
    """
    
    day_name = datetime.now().strftime("%A")
    return send_email(f"🍽️ Today's Meal Plan: {dn_title} ({day_name})", html)



@app.route('/debug-recipes')
def debug_recipes_route():
    recipes = meal_planner.get_recipes_from_db()
    return str(recipes), 200

# --- Scheduler Setup ---

def start_scheduler():
    scheduler = BackgroundScheduler(timezone=pytz.timezone(TIMEZONE))
    
    # 1. Daily reminders: Sunday to Friday at 7:00 AM (New York time)
    scheduler.add_job(
        send_daily_reminder_job,
        'cron',
        day_of_week='sun,mon,tue,wed,thu,fri',
        hour=7,
        minute=0,
        id='daily_reminder'
    )
    
    # 2. Saturday Q/A email: Saturdays at 8:00 AM
    scheduler.add_job(
        send_saturday_qa_email_job,
        'cron',
        day_of_week='sat',
        hour=8,
        minute=0,
        id='saturday_qa'
    )
    
    scheduler.start()
    print("Background scheduler started successfully.")


# Start scheduler when Flask context starts
start_scheduler()

if __name__ == '__main__':
    port = int(os.getenv('FLASK_PORT', '9926'))
    app.run(host='0.0.0.0', port=port)
