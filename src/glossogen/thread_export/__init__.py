"""Export one agent's reconstructed conversation thread as a provider-native request.

Reconstructs a finished run agent's pydantic-ai message history (optionally cut
at a round boundary, reusing the same machinery as the protocol probe) and
serializes it into a drop-in Anthropic Messages / OpenAI Chat request body so a
consumer can append their own question and POST it straight to the provider API.
"""
