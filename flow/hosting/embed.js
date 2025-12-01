/**
 * PailFlow Embeddable Meeting Widget
 *
 * Usage:
 * <div id="meeting-container"></div>
 * <script src="https://your-domain.com/embed.js"></script>
 * <script>
 *   PailFlow.init({
 *     container: '#meeting-container',
 *     roomName: 'my-room-123'
 *   });
 * </script>
 */

(function() {
  'use strict';

  // DAILY_DOMAIN will be injected by the server when serving this file
  const DAILY_DOMAIN = null; // Will be replaced by server

  // Load Daily.co SDK if not already loaded
  function loadDailySDK(callback) {
    // If already loaded, call callback immediately
    if (window.Daily) {
      callback();
      return;
    }

    // Check if script is already being loaded
    if (document.querySelector('script[src*="@daily-co/daily-js"]')) {
      // Script tag exists, just wait for it to load
      waitForDaily(callback);
      return;
    }

    // Create and inject the script tag
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/@daily-co/daily-js';
    script.crossOrigin = 'anonymous';
    script.async = true;

    script.onload = () => {
      if (window.Daily) {
        callback();
      } else {
        console.error('PailFlow: Daily.co SDK loaded but window.Daily is not available');
      }
    };

    script.onerror = () => {
      console.error('PailFlow: Failed to load Daily.co SDK from CDN');
    };

    // Insert script into the document
    const firstScript = document.getElementsByTagName('script')[0];
    if (firstScript && firstScript.parentNode) {
      firstScript.parentNode.insertBefore(script, firstScript);
    } else {
      document.head.appendChild(script);
    }
  }

  // Wait for Daily.co SDK to load (helper function)
  function waitForDaily(callback) {
    if (window.Daily) {
      callback();
      return;
    }

    // Check every 100ms for Daily.co SDK
    const checkInterval = setInterval(() => {
      if (window.Daily) {
        clearInterval(checkInterval);
        callback();
      }
    }, 100);

    // Timeout after 10 seconds
    setTimeout(() => {
      clearInterval(checkInterval);
      if (!window.Daily) {
        console.error('PailFlow: Daily.co SDK failed to load after 10 seconds');
      }
    }, 10000);
  }

  // Create the HTML structure for the widget
  function createWidgetHTML(config) {
    const accentColor = config.accentColor || '#1f2de6';
    const logoText = config.logoText || 'PailFlow';
    const showHeader = config.showHeader !== false; // Default true
    const showBrandLine = config.showBrandLine !== false; // Default true

    return `
      <div class="pailflow-widget">
        ${showBrandLine ? `<div class="pailflow-brand-line" style="height: 4px; width: 100%; background-color: ${accentColor};"></div>` : ''}

        ${showHeader ? `
        <header class="pailflow-header" style="background-color: #ffffff; border-bottom: 1px solid #e2e8f0; height: 72px; display: flex; align-items: center; justify-content: space-between; padding: 0 24px;">
          <div style="display: flex; align-items: center; gap: 16px;">
            <div style="display: flex; align-items: center; gap: 12px;">
              <div style="width: 32px; height: 32px; background-color: ${accentColor}; border-radius: 4px; display: flex; align-items: center; justify-content: center;">
                <svg xmlns="http://www.w3.org/2000/svg" style="width: 20px; height: 20px; color: #ffffff;" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <div style="display: flex; flex-direction: column; justify-content: center;">
                <span class="pailflow-logo-text" style="font-weight: 700; font-size: 18px; line-height: 1; letter-spacing: -0.025em; color: #0f172a;">${logoText}</span>
                <span style="font-size: 10px; font-weight: 600; color: #94a3b8; letter-spacing: 0.1em; text-transform: uppercase; margin-top: 2px;">Workspace</span>
              </div>
            </div>
          </div>
          <div class="pailflow-status" style="display: none; align-items: center; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 9999px; padding: 6px 12px; gap: 8px;">
            <div style="position: relative; display: flex; height: 10px; width: 10px;">
              <span style="animation: ping 2s cubic-bezier(0, 0, 0.2, 1) infinite; position: absolute; display: inline-flex; height: 100%; width: 100%; border-radius: 9999px; background-color: #34d399; opacity: 0.75;"></span>
              <span style="position: relative; display: inline-flex; border-radius: 9999px; height: 10px; width: 10px; background-color: #10b981;"></span>
            </div>
            <span style="font-size: 12px; font-weight: 600; color: #475569;">System Ready</span>
          </div>
        </header>
        ` : ''}

        <main class="pailflow-main" style="flex: 1; position: relative; width: 100%; min-height: 500px; height: 100%; background-color: #ffffff; display: flex; flex-direction: column; overflow: hidden;">
          <div id="pailflow-loading" class="pailflow-loading" style="position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; z-index: 10; background-color: #ffffff; transition: opacity 0.5s;">
            <div class="pailflow-loader-dots" style="display: flex; gap: 8px; margin-bottom: 32px;">
              <div style="width: 12px; height: 12px; background-color: ${accentColor}; border-radius: 50%; animation: bounce 1.4s infinite ease-in-out both; animation-delay: -0.32s;"></div>
              <div style="width: 12px; height: 12px; background-color: ${accentColor}; border-radius: 50%; animation: bounce 1.4s infinite ease-in-out both; animation-delay: -0.16s;"></div>
              <div style="width: 12px; height: 12px; background-color: ${accentColor}; border-radius: 50%; animation: bounce 1.4s infinite ease-in-out both;"></div>
            </div>
            <h2 style="font-size: 20px; font-weight: 600; color: #0f172a;">Joining Meeting</h2>
            <p style="color: #64748b; margin-top: 8px; font-size: 14px;">Establishing secure connection...</p>
          </div>

          <div id="pailflow-error" class="pailflow-error" style="display: none; position: absolute; inset: 0; z-index: 20; flex-direction: column; align-items: center; justify-content: center; background-color: #ffffff; padding: 32px;">
            <div style="width: 48px; height: 48px; background-color: #fee2e2; border-radius: 9999px; display: flex; align-items: center; justify-content: center; margin-bottom: 16px;">
              <svg xmlns="http://www.w3.org/2000/svg" style="width: 24px; height: 24px; color: #dc2626;" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h3 style="font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 8px;">Connection Failed</h3>
            <p id="pailflow-error-message" style="color: #64748b; text-align: center; max-width: 28rem; margin-bottom: 24px;">We couldn't connect you to the room.</p>
            <button onclick="window.location.reload()" style="padding: 10px 24px; background-color: #0f172a; color: #ffffff; border-radius: 6px; font-size: 14px; font-weight: 500; border: none; cursor: pointer; transition: background-color 0.2s;" onmouseover="this.style.backgroundColor='#1e293b'" onmouseout="this.style.backgroundColor='#0f172a'">
              Reload Page
            </button>
          </div>

          <div id="pailflow-daily-frame" class="pailflow-daily-frame" style="width: 100%; flex: 1; min-height: 500px; height: 100%; position: relative; opacity: 0; transition: opacity 0.7s;"></div>
        </main>
      </div>
    `;
  }

  // Inject CSS styles
  function injectStyles() {
    if (document.getElementById('pailflow-widget-styles')) {
      return; // Already injected
    }

    const style = document.createElement('style');
    style.id = 'pailflow-widget-styles';
    style.textContent = `
      .pailflow-widget {
        display: flex;
        flex-direction: column;
        height: 100%;
        min-height: 700px;
        width: 100%;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        box-sizing: border-box;
        overflow: hidden;
      }

      .pailflow-widget * {
        box-sizing: border-box;
      }

      .pailflow-main {
        flex: 1 1 auto;
        min-height: 500px;
        display: flex;
        flex-direction: column;
        position: relative;
        overflow: hidden;
      }

      .pailflow-daily-frame {
        flex: 1 1 auto;
        min-height: 500px;
        position: relative;
        width: 100%;
        height: 100%;
        overflow: hidden;
      }

      .pailflow-daily-frame iframe,
      .pailflow-daily-frame > div {
        width: 100% !important;
        height: 100% !important;
        min-height: 500px !important;
        border: none !important;
        display: block !important;
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
      }

      @keyframes bounce {
        0%, 80%, 100% {
          transform: scale(0);
        }
        40% {
          transform: scale(1);
        }
      }

      @keyframes ping {
        75%, 100% {
          transform: scale(2);
          opacity: 0;
        }
      }

      @media (min-width: 640px) {
        .pailflow-status {
          display: flex !important;
        }
      }
    `;
    document.head.appendChild(style);
  }

  // Main initialization function
  function init(config) {
    // Validate required config
    if (!config.container) {
      console.error('PailFlow: container is required. Example: PailFlow.init({ container: "#my-container", roomName: "room-123" })');
      return;
    }

    if (!config.roomName) {
      console.error('PailFlow: roomName is required. Example: PailFlow.init({ container: "#my-container", roomName: "room-123" })');
      return;
    }

    if (!DAILY_DOMAIN) {
      console.error('PailFlow: DAILY_DOMAIN is not configured. Please contact support.');
      return;
    }

    // Get container element
    const containerEl = typeof config.container === 'string'
      ? document.querySelector(config.container)
      : config.container;

    if (!containerEl) {
      console.error('PailFlow: Container element not found:', config.container);
      return;
    }

    // Inject styles
    injectStyles();

    // Build and inject HTML
    containerEl.innerHTML = createWidgetHTML(config);
    containerEl.style.display = 'flex';
    containerEl.style.flexDirection = 'column';
    containerEl.style.height = '100%';
    containerEl.style.minHeight = '700px';
    containerEl.style.width = '100%';
    containerEl.style.overflow = 'hidden';

    // Get references to elements
    const loadingEl = document.getElementById('pailflow-loading');
    const errorEl = document.getElementById('pailflow-error');
    const errorMsg = document.getElementById('pailflow-error-message');
    const dailyFrameEl = document.getElementById('pailflow-daily-frame');

    // Load Daily.co SDK (if needed), then initialize
    loadDailySDK(() => {
      const roomUrl = `${DAILY_DOMAIN}/${config.roomName}`;
      const accentColor = config.accentColor || '#1f2de6';

      try {
        const dailyFrame = window.Daily.createFrame(dailyFrameEl, {
          activeSpeakerMode: false,
          showLeaveButton: true,
          iframeStyle: {
            width: '100%',
            height: '100%',
            minHeight: '500px',
            border: 'none',
            display: 'block',
            position: 'absolute',
            top: '0',
            left: '0',
          },
          theme: {
            colors: {
              accent: accentColor,
              accentText: '#ffffff',
              mainAreaBg: '#ffffff',
              mainAreaText: '#1e293b',
              mainAreaBgAccent: '#ffffff',
              background: '#ffffff',
              baseText: '#334155',
              border: '#e2e8f0',
            }
          },
        });

        // Event handlers
        dailyFrame.on('loaded', () => {
          // Force the iframe to expand to full height
          if (dailyFrameEl) {
            const iframe = dailyFrameEl.querySelector('iframe');
            if (iframe) {
              iframe.style.height = '100%';
              iframe.style.minHeight = '500px';
              iframe.style.position = 'absolute';
              iframe.style.top = '0';
              iframe.style.left = '0';
              iframe.style.width = '100%';
            }
          }
          if (loadingEl) {
            loadingEl.style.opacity = '0';
            setTimeout(() => {
              if (loadingEl) loadingEl.style.display = 'none';
              if (dailyFrameEl) dailyFrameEl.style.opacity = '1';
            }, 500);
          }
          if (config.onLoaded) config.onLoaded();
        });

        dailyFrame.on('error', (error) => {
          console.error('PailFlow Daily Error:', error);
          if (loadingEl) {
            loadingEl.style.opacity = '0';
            setTimeout(() => {
              if (loadingEl) loadingEl.style.display = 'none';
              if (errorMsg) {
                errorMsg.textContent = error?.errorMsg || 'Failed to join meeting room.';
              }
              if (errorEl) {
                errorEl.style.display = 'flex';
              }
            }, 500);
          }
          if (config.onError) config.onError(error);
        });

        dailyFrame.on('joined-meeting', () => {
          console.log('PailFlow: User joined meeting');
          if (config.onJoined) config.onJoined();
        });

        dailyFrame.on('left-meeting', () => {
          console.log('PailFlow: User left meeting');
          if (config.onLeft) config.onLeft();
        });

        dailyFrame.on('recording-started', () => {
          console.log('PailFlow: Recording started');
          if (config.onRecordingStarted) config.onRecordingStarted();
        });

        dailyFrame.on('recording-stopped', () => {
          console.log('PailFlow: Recording stopped');
          if (config.onRecordingStopped) config.onRecordingStopped();
        });

        dailyFrame.on('recording-error', (error) => {
          console.error('PailFlow: Recording error:', error);
          if (config.onRecordingError) config.onRecordingError(error);
        });

        dailyFrame.on('transcription-started', () => {
          console.log('PailFlow: Transcription started');
          if (config.onTranscriptionStarted) config.onTranscriptionStarted();
        });

        dailyFrame.on('transcription-stopped', () => {
          console.log('PailFlow: Transcription stopped');
          if (config.onTranscriptionStopped) config.onTranscriptionStopped();
        });

        dailyFrame.on('transcription-error', (error) => {
          console.error('PailFlow: Transcription error:', error);
          if (config.onTranscriptionError) config.onTranscriptionError(error);
        });

        // Auto-start features
        if (config.autoRecord || config.autoTranscribe) {
          dailyFrame.on('joined-meeting', async () => {
            async function startFeature(featureName, startFn) {
              try {
                await startFn();
                console.log(`PailFlow: ${featureName} started`);
              } catch (error) {
                const msg = error?.message || error?.error || '';
                if (!msg.includes('already started') && !msg.includes('not enabled')) {
                  console.error(`PailFlow: Failed to start ${featureName}:`, error);
                }
              }
            }

            if (config.autoRecord) {
              startFeature('recording', () => dailyFrame.startRecording());
            }
            if (config.autoTranscribe) {
              startFeature('transcription', () => dailyFrame.startTranscription());
            }
          });
        }

        // Join the meeting
        const joinOptions = { url: roomUrl };
        if (config.token) {
          joinOptions.token = config.token;
        }

        dailyFrame.join(joinOptions).catch((err) => {
          console.error('PailFlow: Join error:', err);
          if (loadingEl) {
            loadingEl.style.opacity = '0';
            setTimeout(() => {
              if (loadingEl) loadingEl.style.display = 'none';
              if (errorMsg) {
                errorMsg.textContent = 'Could not join meeting room.';
              }
              if (errorEl) {
                errorEl.style.display = 'flex';
              }
            }, 500);
          }
          if (config.onError) config.onError(err);
        });

      } catch (err) {
        console.error('PailFlow: Initialization Error:', err);
        if (loadingEl) {
          loadingEl.style.opacity = '0';
          setTimeout(() => {
            if (loadingEl) loadingEl.style.display = 'none';
            if (errorMsg) {
              errorMsg.textContent = 'Could not initialize video frame.';
            }
            if (errorEl) {
              errorEl.style.display = 'flex';
            }
          }, 500);
        }
        if (config.onError) config.onError(err);
      }
    });
  }

  // Expose PailFlow globally
  window.PailFlow = {
    init: init
  };

})();
