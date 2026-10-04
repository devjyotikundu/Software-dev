"""Conversation starters, picked from the pair's shared interests.

Kept deliberately simple and language-neutral: the prompt is shown in
English and the pair answer in whichever language they're practising.
"""
import random

BY_INTEREST = {
    "technology": ["What app or gadget could you not live without, and why?",
                   "Describe a piece of technology your grandparents would find amazing."],
    "music": ["What song have you had on repeat lately? Describe it without naming it.",
              "Which musician would you most like to see live?"],
    "movies": ["Describe a film you love so your partner can guess it.",
               "Which film would you recommend to someone learning your language?"],
    "sports": ["Which sport do you enjoy watching or playing, and what do you like about it?",
               "Explain the rules of a sport as if your partner has never seen it."],
    "travel": ["Describe the best place you've ever visited.",
               "Plan a three-day trip in your partner's country together."],
    "books": ["What book changed how you see something?",
              "Describe a favourite character without saying their name."],
    "food": ["Explain how to cook a dish from where you grew up.",
             "What food from your partner's culture would you like to try?"],
    "art": ["Describe a painting or photo you love.", "What would you create if you had a week free?"],
    "science": ["What's a scientific fact that still amazes you?", "Explain something you know well in simple words."],
    "gaming": ["Describe a game you'd recommend and why.", "What makes a game fun for you?"],
    "photography": ["Describe a photo you're proud of.", "Where would you go to take your perfect picture?"],
    "history": ["Tell a short story from your region's history.", "Which period of history would you visit?"],
    "nature": ["Describe your favourite place outdoors.", "Which season do you like best, and why?"],
    "fitness": ["How do you like to stay active?", "Describe your ideal morning routine."],
}
GENERAL = [
    "Introduce yourself in three sentences, then ask your partner three questions.",
    "What did you do last weekend? Use as many past-tense verbs as you can.",
    "Describe your neighbourhood so your partner can picture it.",
    "What's a phrase in your language that doesn't translate well?",
    "What are you looking forward to this month?",
]


def starters_for(interest_slugs, *, seed=None, count=4):
    """A short, shuffled list: shared-interest prompts first, then general ones."""
    rng = random.Random(seed)
    themed = [prompt for slug in interest_slugs for prompt in BY_INTEREST.get(slug, [])]
    rng.shuffle(themed)
    general = GENERAL[:]
    rng.shuffle(general)
    return (themed + general)[:count]
