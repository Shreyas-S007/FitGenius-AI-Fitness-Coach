from flask import Flask, render_template, request, session, redirect, url_for
from markupsafe import Markup
from agno.agent import Agent
from agno.models.google import Gemini
import os
from datetime import timedelta
import re

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = timedelta(days=1)


def format_model_output(text):
    """Format the model output to be more readable"""
    # Replace any markdown syntax for better HTML display
    # Convert markdown lists to HTML lists
    text = re.sub(r'^\s*-\s+(.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    text = re.sub(r'<li>.*?</li>',
                  lambda m: '<ul>' + m.group(0) + '</ul>' if not re.search(r'<ul>.*?</ul>', m.group(0)) else m.group(0),
                  text, flags=re.DOTALL)

    # Convert markdown headers
    text = re.sub(r'^#+\s+(.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)

    # Convert markdown bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # Convert markdown italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

    # Ensure newlines are preserved
    text = text.replace('\n', '<br>')

    return Markup(text)


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'generate_plan' in request.form:
            # Get form data
            age = request.form.get('age')
            weight = request.form.get('weight')
            height = request.form.get('height')
            sex = request.form.get('sex')
            activity_level = request.form.get('activity_level')
            dietary_preferences = request.form.get('dietary_preferences')
            fitness_goals = request.form.get('fitness_goals')
            gemini_api_key = request.form.get('gemini_api_key')

            # Save API key to session
            session['gemini_api_key'] = gemini_api_key

            try:
                # Initialize Gemini model
                gemini_model = Gemini(id="gemini-1.5-flash", api_key=gemini_api_key)

                # Create user profile
                user_profile = f"""
                Age: {age}
                Weight: {weight}kg
                Height: {height}cm
                Sex: {sex}
                Activity Level: {activity_level}
                Dietary Preferences: {dietary_preferences}
                Fitness Goals: {fitness_goals}
                """

                # Initialize dietary agent
                dietary_agent = Agent(
                    name="Dietary Expert",
                    role="Provides personalized dietary recommendations",
                    model=gemini_model,
                    instructions=[
                        "Consider the user's input, including dietary restrictions and preferences.",
                        "Suggest a detailed meal plan for the day, including breakfast, lunch, dinner, and snacks.",
                        "Use a clear structure with sections for Breakfast, Lunch, Dinner, and Snacks.",
                        "Format your response with clear sections and bullet points for better readability.",
                        "Provide a brief explanation of why the plan is suited to the user's goals.",
                        "Focus on clarity, coherence, and quality of the recommendations.",
                    ]
                )

                # Initialize fitness agent
                fitness_agent = Agent(
                    name="Fitness Expert",
                    role="Provides personalized fitness recommendations",
                    model=gemini_model,
                    instructions=[
                        "Provide exercises tailored to the user's goals.",
                        "Structure your response with clear sections: Warm-up, Main Workout, and Cool-down.",
                        "Use bullet points for exercise lists to improve readability.",
                        "Explain the benefits of each recommended exercise.",
                        "Ensure the plan is actionable and detailed with structured formatting.",
                    ]
                )

                # Get dietary plan
                dietary_plan_response = dietary_agent.run(user_profile)
                dietary_plan = {
                    "why_this_plan_works": "High Protein, Healthy Fats, Moderate Carbohydrates, and Caloric Balance",
                    "meal_plan": dietary_plan_response.content,
                    "important_considerations": [
                        "Hydration: Drink plenty of water throughout the day",
                        "Electrolytes: Monitor sodium, potassium, and magnesium levels",
                        "Fiber: Ensure adequate intake through vegetables and fruits",
                        "Listen to your body: Adjust portion sizes as needed"
                    ]
                }

                # Get fitness plan
                fitness_plan_response = fitness_agent.run(user_profile)
                fitness_plan = {
                    "goals": "Build strength, improve endurance, and maintain overall fitness",
                    "routine": fitness_plan_response.content,
                    "tips": [
                        "Track your progress regularly",
                        "Allow proper rest between workouts",
                        "Focus on proper form",
                        "Stay consistent with your routine"
                    ]
                }

                # Save plans to session
                session['dietary_plan'] = dietary_plan
                session['fitness_plan'] = fitness_plan
                session['plans_generated'] = True
                session['qa_pairs'] = []

                return render_template(
                    'plans.html',
                    dietary_plan=dietary_plan,
                    fitness_plan=fitness_plan,
                    qa_pairs=session.get('qa_pairs', [])
                )

            except Exception as e:
                error_message = f"An error occurred: {str(e)}"
                return render_template('index.html', error_message=error_message)

        elif 'ask_question' in request.form:
            question = request.form.get('question')

            if question and session.get('plans_generated'):
                try:
                    # Get plans from session
                    dietary_plan = session.get('dietary_plan', {})
                    fitness_plan = session.get('fitness_plan', {})
                    gemini_api_key = session.get('gemini_api_key', '')

                    # Initialize Gemini model
                    gemini_model = Gemini(id="gemini-1.5-flash", api_key=gemini_api_key)

                    # Create context
                    context = f"Dietary Plan: {dietary_plan.get('meal_plan', '')}\n\nFitness Plan: {fitness_plan.get('routine', '')}"
                    full_context = f"{context}\nUser Question: {question}"

                    # Get answer
                    agent = Agent(model=gemini_model, show_tool_calls=True, markdown=True)
                    run_response = agent.run(full_context)

                    if hasattr(run_response, 'content'):
                        answer = format_model_output(run_response.content)
                    else:
                        answer = "Sorry, I couldn't generate a response at this time."

                    # Save question and answer to session
                    qa_pairs = session.get('qa_pairs', [])
                    qa_pairs.append((question, answer))
                    session['qa_pairs'] = qa_pairs

                    return render_template(
                        'plans.html',
                        dietary_plan=dietary_plan,
                        fitness_plan=fitness_plan,
                        qa_pairs=qa_pairs
                    )

                except Exception as e:
                    error_message = f"An error occurred while getting the answer: {str(e)}"
                    return render_template(
                        'plans.html',
                        dietary_plan=session.get('dietary_plan', {}),
                        fitness_plan=session.get('fitness_plan', {}),
                        qa_pairs=session.get('qa_pairs', []),
                        error_message=error_message
                    )

    # GET request or no form submitted
    return render_template('index.html')


if __name__ == "__main__":
    app.run(debug=True)