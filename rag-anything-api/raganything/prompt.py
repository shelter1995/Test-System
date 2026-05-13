"""
Prompt templates for multimodal content processing

Contains all prompt templates used in modal processors for analyzing
different types of content (images, tables, equations, etc.)
"""

from __future__ import annotations
from collections.abc import ItemsView, Iterator, KeysView, ValuesView
from typing import Any


class PromptRegistry:
    """Stable prompt container with atomic snapshot swapping.

    Readers keep a reference to this object, while language switches replace the
    underlying prompt dictionary in one step via :meth:`swap`.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def swap(self, prompts: dict[str, Any]) -> None:
        """Atomically replace the active prompt snapshot."""
        self._data = dict(prompts)

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of the active prompt set."""
        return dict(self._data)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self) -> KeysView[str]:
        return self._data.keys()

    def items(self) -> ItemsView[str, Any]:
        return self._data.items()

    def values(self) -> ValuesView[Any]:
        return self._data.values()

    def __repr__(self) -> str:
        return f"PromptRegistry({self._data!r})"


PROMPTS = PromptRegistry()

# System prompts for different analysis types
PROMPTS["IMAGE_ANALYSIS_SYSTEM"] = (
    "You are an expert image analyst. Provide detailed, accurate descriptions."
)
PROMPTS["IMAGE_ANALYSIS_FALLBACK_SYSTEM"] = (
    "You are an expert image analyst. Provide detailed analysis based on available information."
)
PROMPTS["TABLE_ANALYSIS_SYSTEM"] = (
    "You are an expert data analyst. Provide detailed table analysis with specific insights."
)
PROMPTS["EQUATION_ANALYSIS_SYSTEM"] = (
    "You are an expert mathematician. Provide detailed mathematical analysis."
)
PROMPTS["GENERIC_ANALYSIS_SYSTEM"] = (
    "You are an expert content analyst specializing in {content_type} content."
)

# Image analysis prompt template
PROMPTS[
    "vision_prompt"
] = """Please analyze this image in detail and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive and detailed visual description of the image following these guidelines:
    - Describe the overall composition and layout
    - Identify all objects, people, text, and visual elements
    - Explain relationships between elements
    - Note colors, lighting, and visual style
    - Describe any actions or activities shown
    - Include technical details if relevant (charts, diagrams, etc.)
    - Always use specific names instead of pronouns",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "image",
        "summary": "concise summary of the image content and its significance (max 100 words)"
    }}
}}

Additional context:
- Image Path: {image_path}
- Captions: {captions}
- Footnotes: {footnotes}

Focus on providing accurate, detailed visual analysis that would be useful for knowledge retrieval."""

# Image analysis prompt with context support
PROMPTS[
    "vision_prompt_with_context"
] = """Please analyze this image in detail, considering the surrounding context. Provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive and detailed visual description of the image following these guidelines:
    - Describe the overall composition and layout
    - Identify all objects, people, text, and visual elements
    - Explain relationships between elements and how they relate to the surrounding context
    - Note colors, lighting, and visual style
    - Describe any actions or activities shown
    - Include technical details if relevant (charts, diagrams, etc.)
    - Reference connections to the surrounding content when relevant
    - Always use specific names instead of pronouns",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "image",
        "summary": "concise summary of the image content, its significance, and relationship to surrounding content (max 100 words)"
    }}
}}

Context from surrounding content:
{context}

Image details:
- Image Path: {image_path}
- Captions: {captions}
- Footnotes: {footnotes}

Focus on providing accurate, detailed visual analysis that incorporates the context and would be useful for knowledge retrieval."""

# Image analysis prompt with text fallback
PROMPTS["text_prompt"] = """Based on the following image information, provide analysis:

Image Path: {image_path}
Captions: {captions}
Footnotes: {footnotes}

{vision_prompt}"""

# Table analysis prompt template
PROMPTS[
    "table_prompt"
] = """Please analyze this table content and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive analysis of the table including:
    - Table structure and organization
    - Column headers and their meanings
    - Key data points and patterns
    - Statistical insights and trends
    - Relationships between data elements
    - Significance of the data presented
    Always use specific names and values instead of general references.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "table",
        "summary": "concise summary of the table's purpose and key findings (max 100 words)"
    }}
}}

Table Information:
Image Path: {table_img_path}
Caption: {table_caption}
Body: {table_body}
Footnotes: {table_footnote}

Focus on extracting meaningful insights and relationships from the tabular data."""

# Table analysis prompt with context support
PROMPTS[
    "table_prompt_with_context"
] = """Please analyze this table content considering the surrounding context, and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive analysis of the table including:
    - Table structure and organization
    - Column headers and their meanings
    - Key data points and patterns
    - Statistical insights and trends
    - Relationships between data elements
    - Significance of the data presented in relation to surrounding context
    - How the table supports or illustrates concepts from the surrounding content
    Always use specific names and values instead of general references.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "table",
        "summary": "concise summary of the table's purpose, key findings, and relationship to surrounding content (max 100 words)"
    }}
}}

Context from surrounding content:
{context}

Table Information:
Image Path: {table_img_path}
Caption: {table_caption}
Body: {table_body}
Footnotes: {table_footnote}

Focus on extracting meaningful insights and relationships from the tabular data in the context of the surrounding content."""

# Equation analysis prompt template
PROMPTS[
    "equation_prompt"
] = """Please analyze this mathematical equation and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive analysis of the equation including:
    - Mathematical meaning and interpretation
    - Variables and their definitions
    - Mathematical operations and functions used
    - Application domain and context
    - Physical or theoretical significance
    - Relationship to other mathematical concepts
    - Practical applications or use cases
    Always use specific mathematical terminology.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "equation",
        "summary": "concise summary of the equation's purpose and significance (max 100 words)"
    }}
}}

Equation Information:
Equation: {equation_text}
Format: {equation_format}

Focus on providing mathematical insights and explaining the equation's significance."""

# Equation analysis prompt with context support
PROMPTS[
    "equation_prompt_with_context"
] = """Please analyze this mathematical equation considering the surrounding context, and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive analysis of the equation including:
    - Mathematical meaning and interpretation
    - Variables and their definitions in the context of surrounding content
    - Mathematical operations and functions used
    - Application domain and context based on surrounding material
    - Physical or theoretical significance
    - Relationship to other mathematical concepts mentioned in the context
    - Practical applications or use cases
    - How the equation relates to the broader discussion or framework
    Always use specific mathematical terminology.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "equation",
        "summary": "concise summary of the equation's purpose, significance, and role in the surrounding context (max 100 words)"
    }}
}}

Context from surrounding content:
{context}

Equation Information:
Equation: {equation_text}
Format: {equation_format}

Focus on providing mathematical insights and explaining the equation's significance within the broader context."""

# Generic content analysis prompt template
PROMPTS[
    "generic_prompt"
] = """Please analyze this {content_type} content and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive analysis of the content including:
    - Content structure and organization
    - Key information and elements
    - Relationships between components
    - Context and significance
    - Relevant details for knowledge retrieval
    Always use specific terminology appropriate for {content_type} content.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "{content_type}",
        "summary": "concise summary of the content's purpose and key points (max 100 words)"
    }}
}}

Content: {content}

Focus on extracting meaningful information that would be useful for knowledge retrieval."""

# Generic content analysis prompt with context support
PROMPTS[
    "generic_prompt_with_context"
] = """Please analyze this {content_type} content considering the surrounding context, and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive analysis of the content including:
    - Content structure and organization
    - Key information and elements
    - Relationships between components
    - Context and significance in relation to surrounding content
    - How this content connects to or supports the broader discussion
    - Relevant details for knowledge retrieval
    Always use specific terminology appropriate for {content_type} content.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "{content_type}",
        "summary": "concise summary of the content's purpose, key points, and relationship to surrounding context (max 100 words)"
    }}
}}

Context from surrounding content:
{context}

Content: {content}

Focus on extracting meaningful information that would be useful for knowledge retrieval and understanding the content's role in the broader context."""

# Modal chunk templates
PROMPTS["image_chunk"] = """
Image Content Analysis:
Image Path: {image_path}
Captions: {captions}
Footnotes: {footnotes}

Visual Analysis: {enhanced_caption}"""

PROMPTS["table_chunk"] = """Table Analysis:
Image Path: {table_img_path}
Caption: {table_caption}
Structure: {table_body}
Footnotes: {table_footnote}

Analysis: {enhanced_caption}"""

PROMPTS["equation_chunk"] = """Mathematical Equation Analysis:
Equation: {equation_text}
Format: {equation_format}

Mathematical Analysis: {enhanced_caption}"""

PROMPTS["generic_chunk"] = """{content_type} Content Analysis:
Content: {content}

Analysis: {enhanced_caption}"""

# Video analysis prompt template
PROMPTS[
    "video_prompt"
] = """Please analyze this video content and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive analysis of the video including:
    - Overall content summary and main themes
    - Key visual elements and scenes
    - Important dialogue or narration
    - Temporal progression and narrative structure
    - Significant events or actions
    - Visual style and production elements
    Always use specific names and descriptions instead of general references.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "video",
        "summary": "concise summary of the video's purpose and key content (max 100 words)"
    }}
}}

Video Information:
- Video Path: {video_path}
- Duration: {duration}
- Keyframe Captions: {captions}
- Transcript: {transcript}

Focus on extracting meaningful insights and a cohesive understanding of the video content."""

# Video analysis prompt with context support
PROMPTS[
    "video_prompt_with_context"
] = """Please analyze this video content considering the surrounding context, and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive analysis of the video including:
    - Overall content summary and main themes
    - Key visual elements and scenes
    - Important dialogue or narration
    - Temporal progression and narrative structure
    - Significant events or actions
    - Visual style and production elements
    - Relationship to surrounding content
    Always use specific names and descriptions instead of general references.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "video",
        "summary": "concise summary of the video's purpose, key content, and relationship to surrounding context (max 100 words)"
    }}
}}

Context from surrounding content:
{context}

Video Information:
- Video Path: {video_path}
- Duration: {duration}
- Keyframe Captions: {captions}
- Transcript: {transcript}

Focus on extracting meaningful insights and a cohesive understanding of the video content in context."""

# Audio analysis prompt template
PROMPTS[
    "audio_prompt"
] = """Please analyze this audio content and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive analysis of the audio including:
    - Overall content summary and main themes
    - Key spoken content and dialogue
    - Speaker identification and roles (if discernible)
    - Tone, mood, and emotional content
    - Important information and facts presented
    - Temporal structure and progression
    Always use specific names and terminology instead of general references.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "audio",
        "summary": "concise summary of the audio's purpose and key content (max 100 words)"
    }}
}}

Audio Information:
- Audio Path: {audio_path}
- Duration: {duration}
- Transcript: {transcript}

Focus on extracting meaningful insights from the audio content."""

# Audio analysis prompt with context support
PROMPTS[
    "audio_prompt_with_context"
] = """Please analyze this audio content considering the surrounding context, and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive analysis of the audio including:
    - Overall content summary and main themes
    - Key spoken content and dialogue
    - Speaker identification and roles (if discernible)
    - Tone, mood, and emotional content
    - Important information and facts presented
    - Temporal structure and progression
    - Relationship to surrounding content
    Always use specific names and terminology instead of general references.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "audio",
        "summary": "concise summary of the audio's purpose, key content, and relationship to surrounding context (max 100 words)"
    }}
}}

Context from surrounding content:
{context}

Audio Information:
- Audio Path: {audio_path}
- Duration: {duration}
- Transcript: {transcript}

Focus on extracting meaningful insights from the audio content in context."""

# Modal chunk templates for video and audio
PROMPTS["video_chunk"] = """Video Analysis:
Video Path: {video_path}
Duration: {duration}
Keyframe Captions: {captions}
Transcript: {transcript}

Analysis: {enhanced_caption}"""

PROMPTS["audio_chunk"] = """Audio Analysis:
Audio Path: {audio_path}
Duration: {duration}
Transcript: {transcript}

Analysis: {enhanced_caption}"""

# Query-related prompts
PROMPTS["QUERY_IMAGE_DESCRIPTION"] = (
    "Please briefly describe the main content, key elements, and important information in this image."
)

PROMPTS["QUERY_IMAGE_ANALYST_SYSTEM"] = (
    "You are a professional image analyst who can accurately describe image content."
)

PROMPTS[
    "QUERY_TABLE_ANALYSIS"
] = """Please analyze the main content, structure, and key information of the following table data:

Table data:
{table_data}

Table caption: {table_caption}

Please briefly summarize the main content, data characteristics, and important findings of the table."""

PROMPTS["QUERY_TABLE_ANALYST_SYSTEM"] = (
    "You are a professional data analyst who can accurately analyze table data."
)

PROMPTS[
    "QUERY_EQUATION_ANALYSIS"
] = """Please explain the meaning and purpose of the following mathematical formula:

LaTeX formula: {latex}
Formula caption: {equation_caption}

Please briefly explain the mathematical meaning, application scenarios, and importance of this formula."""

PROMPTS["QUERY_EQUATION_ANALYST_SYSTEM"] = (
    "You are a mathematics expert who can clearly explain mathematical formulas."
)

PROMPTS[
    "QUERY_GENERIC_ANALYSIS"
] = """Please analyze the following {content_type} type content and extract its main information and key features:

Content: {content_str}

Please briefly summarize the main characteristics and important information of this content."""

PROMPTS["QUERY_GENERIC_ANALYST_SYSTEM"] = (
    "You are a professional content analyst who can accurately analyze {content_type} type content."
)

PROMPTS["QUERY_ENHANCEMENT_SUFFIX"] = (
    "\n\nPlease provide a comprehensive answer based on the user query and the provided multimodal content information."
)
