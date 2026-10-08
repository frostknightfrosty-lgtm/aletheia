# Phase 5 — Social / Geospatial / Image

Phase 5 adds eight adapters while preserving the typed adapter boundary and Phase 1–4 provenance/checkpoint behavior.

## Social

- Instaloader 4.15.3: unauthenticated public Instagram profile metadata only.
- Reddit API v1: official OAuth user-overview endpoint using operator credentials.
- YouTube Data API v3: official channel discovery/read-only metadata using an API key.

## Geospatial

- Overpass public API: read-only OpenStreetMap-derived nearby named-place lookup around an authorized coordinate.
- SunCalc 2.0.2: offline solar position and daylight-phase calculation.

## Image

- DeepFace 0.0.101: offline face detection through its OpenCV backend; no identity recognition.
- InsightFace 2.1: offline face detection when licensed model weights are operator-provisioned; network-disabled by design.
- Google Cloud Vision 3.16.0: labels, OCR, and face detection for operator-supplied images.

## Deferred

TikTok Research API remains deferred because Research Tools require qualifying researcher access and approval; no unofficial scraping path is added. Sentinel Hub, TinEye, ImageHash/pHash, FaceRecognition, Telegram public-channel access, and additional social forks remain deferred until current API/version/license details can be pinned without guessing or introducing replacement implementations.
