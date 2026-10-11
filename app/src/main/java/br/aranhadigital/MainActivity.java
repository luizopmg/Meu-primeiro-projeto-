package br.aranhadigital;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Aranha Digital: a interface inteira é a página assets/index.html dentro de um WebView.
 * Esta classe só faz o que a página não consegue sozinha:
 *  - pedidos HTTP para outros sites (sem o bloqueio CORS do navegador);
 *  - escolher um arquivo mapa.json no celular;
 *  - salvar mapa.json e relatorio.csv na pasta Download/AranhaDigital;
 *  - abrir links no navegador do celular.
 */
public class MainActivity extends Activity {
    private static final int PICK_FILE = 41;
    private static final int MAX_BYTES = 3_000_000;
    private static final int MAX_REDIRECTS = 6;
    private static final Pattern META_CHARSET =
            Pattern.compile("<meta[^>]+charset\\s*=\\s*[\"']?([A-Za-z0-9_\\-]+)", Pattern.CASE_INSENSITIVE);

    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private final ExecutorService pool = Executors.newFixedThreadPool(2);

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        web.setBackgroundColor(0xFF05070D);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);          // guarda o último mapa e as opções
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setMediaPlaybackRequiresUserGesture(true);

        web.addJavascriptInterface(new Bridge(), "AranhaNative");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                if ("file".equals(u.getScheme())) return false;
                openExternal(u.toString());      // links de sites abrem no navegador
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("*/*");
                pick.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/json", "text/plain", "application/octet-stream"});
                try {
                    startActivityForResult(Intent.createChooser(pick, "Abrir mapa.json"), PICK_FILE);
                    return true;
                } catch (ActivityNotFoundException e) {
                    fileCallback = null;
                    return false;
                }
            }
        });

        if (state != null) web.restoreState(state);
        else web.loadUrl("file:///android_asset/index.html");
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == PICK_FILE && fileCallback != null) {
            Uri[] result = null;
            if (resultCode == RESULT_OK && data != null && data.getData() != null) result = new Uri[]{data.getData()};
            fileCallback.onReceiveValue(result);
            fileCallback = null;
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        pool.shutdownNow();
        web.destroy();
        super.onDestroy();
    }

    private void openExternal(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception e) {
            Toast.makeText(this, "Nenhum app para abrir este link", Toast.LENGTH_SHORT).show();
        }
    }

    /** Métodos chamados pela página (window.AranhaNative.*). */
    private class Bridge {
        @JavascriptInterface
        public void fetch(final String id, final String url, final String userAgent) {
            pool.execute(() -> {
                JSONObject r = download(url, userAgent);
                try { r.put("id", id); } catch (JSONException ignored) { }
                final String js = "window.__aranhaDone(" + r.toString() + ")";
                web.post(() -> web.evaluateJavascript(js, null));
            });
        }

        @JavascriptInterface
        public String saveFile(String name, String content) {
            return save(name.replaceAll("[\\\\/:*?\"<>|]", "_"), content);
        }

        @JavascriptInterface
        public void openUrl(final String url) {
            if (url != null && (url.startsWith("http://") || url.startsWith("https://"))) runOnUiThread(() -> openExternal(url));
        }

        @JavascriptInterface
        public String version() {
            return "2.2";
        }
    }

    /** GET que segue redirecionamentos manualmente, para saber o endereço final. */
    private JSONObject download(String startUrl, String userAgent) {
        JSONObject r = new JSONObject();
        HttpURLConnection c = null;
        long t0 = System.nanoTime();
        try {
            String current = startUrl;
            int code;
            int hops = 0;
            while (true) {
                URL u = new URL(current);
                String proto = u.getProtocol();
                if (!"http".equals(proto) && !"https".equals(proto)) throw new IllegalArgumentException("endereço não é http(s)");
                c = (HttpURLConnection) u.openConnection();
                c.setInstanceFollowRedirects(false);
                c.setConnectTimeout(15000);
                c.setReadTimeout(20000);
                c.setRequestProperty("User-Agent", userAgent);
                c.setRequestProperty("Accept", "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5");
                c.setRequestProperty("Accept-Language", "pt-BR,pt;q=0.9,en;q=0.7");
                code = c.getResponseCode();
                String loc = c.getHeaderField("Location");
                if (code >= 300 && code < 400 && loc != null && hops < MAX_REDIRECTS) {
                    current = new URL(u, loc).toString();
                    c.disconnect();
                    hops++;
                    continue;
                }
                break;
            }
            String type = c.getContentType();
            r.put("ok", true);
            r.put("status", code);
            r.put("url", current);
            r.put("contentType", type == null ? "" : type);
            String ra = c.getHeaderField("Retry-After");
            r.put("retryAfter", ra == null ? "" : ra);
            // todos os cabeçalhos, em minúsculas (ex.: crawler-price do protocolo HTTP 402)
            JSONObject headers = new JSONObject();
            for (Map.Entry<String, List<String>> h : c.getHeaderFields().entrySet()) {
                if (h.getKey() == null || h.getValue() == null) continue;
                StringBuilder v = new StringBuilder();
                for (String part : h.getValue()) {
                    if (v.length() > 0) v.append(", ");
                    v.append(part);
                }
                headers.put(h.getKey().toLowerCase(Locale.ROOT), v.toString());
            }
            r.put("headers", headers);

            String lower = type == null ? "" : type.toLowerCase();
            boolean wantBody = lower.isEmpty() || lower.contains("html") || lower.contains("text") || lower.contains("xml");
            byte[] bytes = new byte[0];
            boolean truncated = false;
            if (wantBody) {
                InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
                if (in != null) {
                    ByteArrayOutputStream buf = new ByteArrayOutputStream();
                    byte[] chunk = new byte[16384];
                    int n;
                    while ((n = in.read(chunk)) != -1) {
                        buf.write(chunk, 0, n);
                        if (buf.size() > MAX_BYTES) { truncated = true; break; }
                    }
                    in.close();
                    bytes = buf.toByteArray();
                }
            }
            r.put("ms", (System.nanoTime() - t0) / 1_000_000);
            r.put("bytes", bytes.length);
            r.put("truncated", truncated);
            r.put("body", new String(bytes, pickCharset(type, bytes)));
        } catch (Exception e) {
            try {
                r.put("ok", false);
                String msg = e.getMessage();
                r.put("error", e.getClass().getSimpleName() + (msg == null ? "" : ": " + msg));
            } catch (JSONException ignored) { }
        } finally {
            if (c != null) c.disconnect();
        }
        return r;
    }

    private static Charset pickCharset(String contentType, byte[] bytes) {
        String name = null;
        if (contentType != null) {
            Matcher m = Pattern.compile("charset=\\s*\"?([A-Za-z0-9_\\-]+)", Pattern.CASE_INSENSITIVE).matcher(contentType);
            if (m.find()) name = m.group(1);
        }
        if (name == null) {
            String head = new String(bytes, 0, Math.min(bytes.length, 4096), StandardCharsets.ISO_8859_1);
            Matcher m = META_CHARSET.matcher(head);
            if (m.find()) name = m.group(1);
        }
        try {
            if (name != null) return Charset.forName(name);
        } catch (Exception ignored) { }
        return StandardCharsets.UTF_8;
    }

    /** Salva em Download/AranhaDigital (Android 10+) ou na pasta do app (Android 7–9). */
    private String save(String name, String content) {
        String mime = name.endsWith(".csv") ? "text/csv" : "application/json";
        byte[] data = content.getBytes(StandardCharsets.UTF_8);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                ContentValues v = new ContentValues();
                v.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                v.put(MediaStore.MediaColumns.MIME_TYPE, mime);
                v.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/AranhaDigital");
                Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                if (uri == null) return "erro: o sistema recusou criar o arquivo";
                try (OutputStream os = getContentResolver().openOutputStream(uri)) {
                    if (os == null) return "erro: não consegui abrir o arquivo";
                    os.write(data);
                }
                return "Download/AranhaDigital/" + name;
            }
            File dir = new File(getExternalFilesDir(null), "AranhaDigital");
            if (!dir.exists() && !dir.mkdirs()) return "erro: não consegui criar a pasta";
            File f = new File(dir, name);
            try (FileOutputStream os = new FileOutputStream(f)) {
                os.write(data);
            }
            return f.getAbsolutePath();
        } catch (Exception e) {
            return "erro: " + e.getMessage();
        }
    }
}
