from textwrap import dedent

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task


@CrewBase
class EmailGenerationCrew:
    @agent
    def style_analyst(self):
        return Agent(
            role="Writing Style Analyst",
            goal="Analyze and understand the respondent's writing style and tone",
            backstory=dedent("""
                Expert in linguistic analysis and writing style recognition.
                Specializes in identifying unique writing patterns, tone, and communication preferences.
            """),
            prompt_template=dedent("""
                You are an expert in linguistic analysis and writing style recognition.
                You specialize in identifying unique writing patterns, tone, and communication preferences.
            """),
            llm="gpt-4o",
            allow_delegation=False,
        )

    @agent
    def context_analyzer(self):
        return Agent(
            role="Context Analyzer",
            goal="Analyze conversation history and extract relevant information",
            backstory=dedent("""
                Expert in conversation analysis and information extraction.
                Specializes in understanding context, identifying key points, and maintaining conversation coherence.
            """),
            prompt_template=dedent("""
                You are an expert in conversation analysis and information extraction.
                You specialize in understanding context, identifying key points, and maintaining conversation coherence.
            """),
            allow_delegation=False,
        )

    @agent
    def email_composer(self):
        return Agent(
            role="Email Composer",
            goal="Generate email responses that match the user's style and context",
            backstory=dedent("""
                Expert email writer with deep understanding of professional communication.
                Specializes in mimicking writing styles and generating contextually appropriate responses.
            """),
            allow_delegation=False,
        )

    @task
    def style_analysis_task(self, conversation_history, user_style_examples):
        # Task 1: Analyze writing style
        return Task(
            description=dedent("""
                Analyze the provided email examples to understand the user's writing style.
                Identify key patterns in:
                - Tone and formality level
                - Common phrases and expressions
                - Greeting and closing styles
                - Paragraph structure and length
                - Use of formatting (bold, italic, lists, etc.)
            """),
            agent=self.style_analyst,
            context={"user_style_examples": user_style_examples},
        )

    @task
    def context_analysis_task(self, conversation_history):
        return Task(
            description=dedent("""
                Analyze the conversation history to understand the context.
                Extract:
                - Key discussion points
                - Important dates, numbers, or references
                - Pending questions or actions
                - Relevant background information
            """),
            agent=self.context_analyzer,
            context={"conversation_history": conversation_history},
        )

    @task
    def email_generation_task(self, style_analysis, context_analysis):
        return Task(
            description=dedent("""
                Generate an email response that:
                1. Matches the user's writing style
                2. Addresses all relevant points from the conversation
                3. Uses appropriate HTML formatting
                4. Maintains conversation coherence
                
                Format using HTML tags:
                - <p> for paragraphs
                - <br> for line breaks
                - <ul>/<ol> with <li> for lists
                - <strong> or <b> for bold text
                - <em> or <i> for italic text
            """),
            agent=self.email_composer,
            context={"style_analysis": style_analysis, "context_analysis": context_analysis},
        )

    @crew
    def crew(self):
        # Create crew and assign tasks
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)


# Example usage
if __name__ == "__main__":
    from email_adapt.gmail.src.user_email_style import GetEmailReferences

    # Sample conversation history and style examples
    conversation_history = [
        {"sender": "user", "content": "Sample previous email content..."},
        {"recipient": "client", "content": "Sample response content..."},
    ]

    # Get the user's style examples
    user_style_examples = [
        x["text"] for x in GetEmailReferences(collection_name="medsriha%40gmail.com").get_references(top_k=5)
    ]

    # Create and run the email generation crew
    email_crew = EmailGenerationCrew()
    generated_email = email_crew.generate_email(conversation_history, user_style_examples)
    print(generated_email)
