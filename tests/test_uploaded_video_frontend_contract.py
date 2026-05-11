from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_uploaded_video_frontend_contract_files_exist():
    required = [
        ROOT / "frontend/src/api/uploadedVideoApi.js",
        ROOT / "frontend/src/hooks/useUploadedVideo.js",
        ROOT / "frontend/src/hooks/useUploadedVideoProgress.js",
        ROOT / "frontend/src/components/uploaded-video/UploadedVideoDropzone.jsx",
        ROOT / "frontend/src/components/uploaded-video/UploadedVideoProcessingPanel.jsx",
        ROOT / "frontend/src/components/uploaded-video/UploadedVideoTimeline.jsx",
        ROOT / "frontend/src/components/uploaded-video/UploadedVideoEventsTable.jsx",
        ROOT / "frontend/src/components/uploaded-video/UploadedVideoClipControls.jsx",
        ROOT / "frontend/src/components/uploaded-video/UploadedVideoReportPanel.jsx",
        ROOT / "frontend/src/components/uploaded-video/CreateCaseFromVideoButton.jsx",
        ROOT / "frontend/src/pages/UploadedVideoAnalysisPage.jsx",
    ]
    for path in required:
        assert path.exists(), str(path)


def test_uploaded_video_frontend_contract_references_route_and_api():
    app_text = (ROOT / "frontend/src/App.jsx").read_text(encoding="utf-8")
    api_text = (ROOT / "frontend/src/api/uploadedVideoApi.js").read_text(encoding="utf-8")

    assert "uploaded-video-analysis" in app_text
    assert "/api/uploaded-videos" in api_text
    assert "/clips/" in api_text and "download" in api_text
