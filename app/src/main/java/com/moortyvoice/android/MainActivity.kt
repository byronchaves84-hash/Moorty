package com.moortyvoice.android

import android.app.Activity
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.media.MediaPlayer
import android.content.Intent
import android.net.Uri
import android.view.ViewGroup
import android.view.Gravity
import android.widget.*
import android.graphics.Color
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : Activity(), TextToSpeech.OnInitListener {
    private lateinit var root: LinearLayout
    private lateinit var tts: TextToSpeech
    private val executor = Executors.newSingleThreadExecutor()
    private var player: MediaPlayer? = null
    private var generalSound: Uri? = null
    private var subscriberSound: Uri? = null
    private var youtubeRunning = false
    private var youtubeThread: Thread? = null
    private lateinit var apiKey: EditText
    private lateinit var liveChatId: EditText
    private lateinit var status: TextView
    private lateinit var volume: SeekBar
    private var volumeValue = 0.8f
    private val recentOnly = true // Required: enabled from launch; no off switch.
    private val spokenIds = LinkedHashSet<String>()
    private var nextPageToken = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        tts = TextToSpeech(this, this)
        buildUi()
    }

    private fun buildUi() {
        val scroll = ScrollView(this)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 20, 24, 32)
            setBackgroundColor(Color.rgb(248, 247, 252))
        }
        scroll.addView(root)
        setContentView(scroll)

        addText("MOORTY VOICE — ANDROID", 24f, true)
        addText("TikTok LIVE + YouTube LIVE · versión Android en adaptación", 14f, false)
        status = addText("Estado: listo", 14f, false)

        addText("VOZ EN ESPAÑOL", 18f, true)
        button("Probar voz") { speak("Prueba de voz de Moorty Voice. El audio está funcionando.") }

        addText("SONIDOS DE ENTRADA — TIKTOK", 18f, true)
        addText("Entrada normal", 14f, true)
        button("Elegir sonido normal (MP3/MPEG/WAV/OGG)") { chooseAudio(1001) }
        button("Probar sonido normal") { playSound(generalSound) }
        addText("Entrada de suscriptor", 14f, true)
        button("Elegir sonido de suscriptor (MP3/MPEG/WAV/OGG)") { chooseAudio(1002) }
        button("Probar sonido de suscriptor") { playSound(subscriberSound) }
        addText("Volumen de efectos", 14f, true)
        volume = SeekBar(this).apply {
            max = 100
            progress = 80
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(s: SeekBar?, p: Int, user: Boolean) { volumeValue = p / 100f }
                override fun onStartTrackingTouch(s: SeekBar?) {}
                override fun onStopTrackingTouch(s: SeekBar?) {}
            })
        }
        root.addView(volume, matchWrap())

        addText("MENSAJES RECIENTES", 18f, true)
        addText("Priorizar SOLO los mensajes más recientes: ACTIVADO SIEMPRE. Los eventos antiguos pendientes se sustituyen por el último evento.", 14f, false)

        addText("YOUTUBE LIVE CHAT", 18f, true)
        apiKey = edit("YouTube Data API v3 — API key")
        liveChatId = edit("liveChatId del directo")
        button("Conectar YouTube") { connectYouTube() }
        button("Desconectar YouTube") { disconnectYouTube() }

        addText("TIKTOK LIVE", 18f, true)
        addText("La interfaz está preparada, pero la conexión TikTok LIVE no está implementada en esta versión Android. La biblioteca TikTokLive del programa Windows no se ejecuta directamente en Android; hace falta un adaptador compatible y probarlo contra un LIVE real.", 14f, false)
        button("Estado de conexión TikTok") {
            status.text = "TikTok: adaptador Android pendiente; no se simula una conexión."
        }

        addText("NOTA", 13f, true)
        addText("Para escuchar en segundo plano y cubrir todas las alertas como en Windows, falta integrar un servicio foreground y completar los adaptadores de plataforma. El código Windows original se incluye en legacy/windows_original.", 13f, false)
    }

    private fun addText(text: String, size: Float, bold: Boolean): TextView {
        val t = TextView(this).apply {
            this.text = text
            textSize = size
            setTextColor(Color.rgb(34, 32, 40))
            if (bold) setTypeface(null, android.graphics.Typeface.BOLD)
            setPadding(0, 10, 0, 10)
        }
        root.addView(t, matchWrap())
        return t
    }

    private fun edit(hintText: String): EditText {
        val e = EditText(this).apply {
            hint = hintText
            textSize = 14f
            singleLine = true
            setPadding(16, 8, 16, 8)
            setBackgroundColor(Color.WHITE)
        }
        root.addView(e, matchWrap())
        return e
    }

    private fun button(label: String, action: () -> Unit) {
        val b = Button(this).apply {
            text = label
            isAllCaps = false
            setOnClickListener { action() }
        }
        root.addView(b, matchWrap())
    }

    private fun matchWrap(): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            bottomMargin = 8
        }

    private fun chooseAudio(requestCode: Int) {
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "audio/*"
            putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg", "application/octet-stream"))
        }
        startActivityForResult(intent, requestCode)
    }

    @Deprecated("Android document picker callback")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (resultCode != Activity.RESULT_OK || data?.data == null) return
        val uri = data.data!!
        contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        if (requestCode == 1001) generalSound = uri
        if (requestCode == 1002) subscriberSound = uri
        status.text = "Audio seleccionado: ${uri.lastPathSegment ?: "archivo"}"
    }

    private fun playSound(uri: Uri?) {
        if (uri == null) {
            status.text = "Seleccioná un archivo de audio primero."
            return
        }
        try {
            player?.release()
            player = MediaPlayer().apply {
                setDataSource(this@MainActivity, uri)
                setVolume(volumeValue, volumeValue)
                setOnPreparedListener { it.start() }
                setOnCompletionListener { it.release(); if (player === it) player = null }
                prepareAsync()
            }
            status.text = "Reproduciendo sonido…"
        } catch (e: Exception) {
            status.text = "No se pudo reproducir ese archivo. Probá con MP3."
        }
    }

    override fun onInit(statusCode: Int) {
        if (statusCode == TextToSpeech.SUCCESS) {
            val result = tts.setLanguage(Locale("es", "ES"))
            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                tts.language = Locale("es")
            }
        }
    }

    private fun speak(text: String) {
        if (::tts.isInitialized) tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "moorty-voice")
    }

    private fun connectYouTube() {
        val key = apiKey.text.toString().trim()
        val chatId = liveChatId.text.toString().trim()
        if (key.isEmpty() || chatId.isEmpty()) {
            status.text = "Introducí la API key y el liveChatId."
            return
        }
        if (youtubeRunning) return
        youtubeRunning = true
        nextPageToken = ""
        status.text = "Conectando a YouTube Live Chat…"
        youtubeThread = Thread {
            while (youtubeRunning) {
                try {
                    val query = "https://www.googleapis.com/youtube/v3/liveChat/messages?liveChatId=$chatId&part=id,snippet,authorDetails&maxResults=200&key=$key" +
                        if (nextPageToken.isNotEmpty()) "&pageToken=$nextPageToken" else ""
                    val conn = (URL(query).openConnection() as HttpURLConnection).apply {
                        connectTimeout = 10000
                        readTimeout = 15000
                        requestMethod = "GET"
                    }
                    val code = conn.responseCode
                    val body = (if (code in 200..299) conn.inputStream else conn.errorStream).bufferedReader().use { it.readText() }
                    if (code !in 200..299) throw Exception("HTTP $code: $body")
                    val json = JSONObject(body)
                    val items = json.optJSONArray("items")
                    nextPageToken = json.optString("nextPageToken", nextPageToken)
                    val events = mutableListOf<Pair<String, String>>()
                    if (items != null) for (i in 0 until items.length()) {
                        val item = items.getJSONObject(i)
                        val id = item.optString("id")
                        val msg = item.optJSONObject("snippet")?.optString("displayMessage", "") ?: ""
                        val author = item.optJSONObject("authorDetails")?.optString("displayName", "Alguien") ?: "Alguien"
                        if (id.isNotBlank() && msg.isNotBlank() && !spokenIds.contains(id)) {
                            spokenIds.add(id)
                            events.add("$author dice $msg" to id)
                        }
                    }
                    // recent-only: speak only the latest unseen message in each poll.
                    val latest = events.lastOrNull()
                    if (latest != null) runOnUiThread {
                        speak(latest.first)
                        status.text = "YouTube conectado · último mensaje: ${latest.first}"
                    }
                    if (spokenIds.size > 1500) spokenIds.clear()
                    conn.disconnect()
                    Thread.sleep(2500)
                } catch (e: Exception) {
                    runOnUiThread { status.text = "YouTube: ${e.message?.take(180) ?: "error"}" }
                    try { Thread.sleep(5000) } catch (_: InterruptedException) {}
                }
            }
        }.apply { isDaemon = true; start() }
    }

    private fun disconnectYouTube() {
        youtubeRunning = false
        youtubeThread?.interrupt()
        status.text = "YouTube desconectado."
    }

    override fun onDestroy() {
        youtubeRunning = false
        player?.release()
        if (::tts.isInitialized) tts.shutdown()
        executor.shutdownNow()
        super.onDestroy()
    }
}
