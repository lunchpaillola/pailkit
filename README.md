# 🧰 PailKit

Tools for builders. Built by [Lunch Pail Labs](https://www.lunchpaillabs.com).
We’re taking [Lunch Pail add-ons](https://addons.lunchpaillabs.com), expanding them, breaking them free, and making them usable anywhere.

PailKit is a growing collection of clean, composable building blocks for creating products —  APIs, widgets, and MCPs designed to work well with humans or AI.


---

### ⚙️ Philosophy

We build for builders. The ones in the arena, shipping, breaking, iterating, trying again.

For the people who want to be better: engineers, product thinkers, creators.

We value:

* Teaching what we know
* Defaults shaped by real product decisions
* Honesty about what works and what doesn’t
* Transparency in how things are built
* Learning as we go
* The joy of showing your work because it’s *good*


We build tools we actually use, the kind we’d recommend to customers, teammates, and friends.

We’re not here to give every option, just a better starting point: reliable, understandable, and easy to extend.

Use our building blocks. Or don’t. Fork it. Rewrite it. Break it. That’s what they’re for.

---

### 📦 Structure

* `/api` — core building blocks for creating and connecting things.
  *Example: `/api/rooms/create` to spin up a new video or audio room.*

* `/mcp` — model context protocol interfaces so your agents can use PailKit capabilities directly.
  *Everything here is designed to be callable by humans or AIs alike.*

* `/widgets` — optional embeddable UI components for when you want visual drop-ins.
  *Think simple, beautiful defaults you can extend.*

* `/docs` — living documentation, examples, and guides.
  *We document what we learn, as we learn it.*


### 🧩 Open Source & Feedback

We’re building this in public.
Follow along, contribute ideas, or request new building blocks on the [PailKit board](https://lunchpaillabs.canny.io/feature-requests?selectedCategory=pailkit).


🎥 Watch the daily founder logs on [YouTube](https://youtube.com/playlist?list=PLtYkNv-KJw4bjT1bErr4RzEoyOYdOsRZX&si=zLYM-xUE-Tlw6ePG).

---

### 🚧 Status

Work in progress. Expect experiments, iteration, and plenty of learning in public. If you want to try it out, send a request for access (**PailKit API key**) and we’ll get you set up: [grab an API key](mailto:help@lunchpaillabs.com?subject=PailKit%20API%20Key%20Request).

---

## 🚀 Roadmap

**v0.1 — Launch Building Block #1: Rooms**
The first building block of PailKit.
A single API and MCP interface for creating and managing rooms — for video, audio, or live collaboration.

* [ ] `POST /api/rooms/create` — create a room in one call
* [ ] `/mcp/rooms/create_room` — agent-callable version


🔗 [Share feedback or request features →](https://lunchpaillabs.canny.io/feature-requests?selectedCategory=pailkit)


**v0.2 — Transcription**

* [ ] `/api/transcribe` — upload or stream audio/video and get a transcript
* [ ] `/mcp/transcribe` — agent-callable capability



**v0.3 — Scheduling**

* [ ] `/api/schedule/create` — create events and link to rooms
* [ ] `/mcp/schedule/create_event` — agent-callable
