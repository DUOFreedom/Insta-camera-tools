package com.duofreedom.instatools

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.duofreedom.instatools.ui.instatoolsApp
import com.duofreedom.instatools.ui.theme.instatoolsTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            instatoolsTheme {
                instatoolsApp()
            }
        }
    }
}
