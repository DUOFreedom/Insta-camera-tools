package com.duofreedom.instaace

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.duofreedom.instaace.ui.InstaAceApp
import com.duofreedom.instaace.ui.theme.InstaAceTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            InstaAceTheme {
                InstaAceApp()
            }
        }
    }
}
