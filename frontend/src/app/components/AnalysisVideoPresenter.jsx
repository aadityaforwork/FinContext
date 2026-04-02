import React, { useState, useEffect, useRef } from "react";

export default function AnalysisVideoPresenter({ memo, ticker, onClose }) {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const synthRef = useRef(null);

  // Prepare slides from the ELI5 memo
  const slides = [];
  if (memo) {
    slides.push({
      text: `Let's talk about ${memo.company}, ticker ${ticker}. I am going to explain their current situation simply so anyone can understand.`,
      display: <h2 className="animate-fade-up text-3xl font-black mb-4">{ticker} <span className="text-gray-400 font-normal block text-xl mt-2">{memo.company}</span></h2>
    });
    
    slides.push({
      text: `Here is the simple explanation. ${memo.analogy}`,
      display: (
        <div className="animate-fade-up">
           <p className="text-indigo-400 text-sm font-bold tracking-widest uppercase mb-2">The Simple Explanation</p>
           <p className="text-2xl leading-relaxed font-medium">"{memo.analogy}"</p>
        </div>
      )
    });

    slides.push({
      text: `I give their overall financial health a score of ${memo.health_score} out of 100.`,
      display: (
        <div className="animate-fade-up flex flex-col items-center">
           <p className="text-gray-400 text-sm font-bold tracking-widest uppercase mb-4">Health Score</p>
           <div className="text-7xl font-black mb-2" style={{ color: memo.health_score > 70 ? "#34d399" : memo.health_score > 40 ? "#f59e0b" : "#ef4444" }}>
             {memo.health_score}
           </div>
           <p className="text-xl font-medium text-gray-300">Out of 100</p>
        </div>
      )
    });

    if (memo.pros && memo.pros.length > 0) {
      const prosText = memo.pros.join(". ");
      slides.push({
        text: `Here is what is going well. ${prosText}`,
        display: (
          <div className="animate-fade-up p-6 rounded-2xl bg-emerald-500/10 border border-emerald-500/20">
            <h3 className="text-emerald-400 font-bold mb-4 flex items-center gap-2">
              <span className="text-2xl">✓</span> What's going well
            </h3>
            <ul className="space-y-4">
              {memo.pros.map((point, i) => (
                <li key={i} className="flex gap-3 text-sm font-medium"><span className="text-emerald-500 font-bold">+</span> {point}</li>
              ))}
            </ul>
          </div>
        )
      });
    }

    if (memo.cons && memo.cons.length > 0) {
      const consText = memo.cons.join(". ");
      slides.push({
        text: `However, here is what to worry about. ${consText}`,
        display: (
          <div className="animate-fade-up p-6 rounded-2xl bg-red-500/10 border border-red-500/20">
            <h3 className="text-red-400 font-bold mb-4 flex items-center gap-2">
              <span className="text-2xl">✕</span> What to worry about
            </h3>
            <ul className="space-y-4">
              {memo.cons.map((point, i) => (
                <li key={i} className="flex gap-3 text-sm font-medium"><span className="text-red-500 font-bold">-</span> {point}</li>
              ))}
            </ul>
          </div>
        )
      });
    }

    slides.push({
      text: `The bottom line. ${memo.bottom_line}. End of story.`,
      display: (
        <div className="animate-fade-up text-center">
          <span className="text-4xl mb-4 block">🎯</span>
          <p className="text-gray-400 text-sm font-bold tracking-widest uppercase mb-2">The Bottom Line</p>
          <p className="text-xl font-medium">{memo.bottom_line}</p>
        </div>
      )
    });
  }

  useEffect(() => {
    // Initialize speech synthesis
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      synthRef.current = window.speechSynthesis;
    }
    
    return () => {
      // Cleanup on unmount
      if (synthRef.current) {
        synthRef.current.cancel();
      }
    };
  }, []);

  useEffect(() => {
    if (isPlaying && synthRef.current && currentSlide < slides.length) {
      // Speak the current slide
      const utterance = new SpeechSynthesisUtterance(slides[currentSlide].text);
      
      // Try to find a good voice (preferably a natural sounding English voice)
      const voices = synthRef.current.getVoices();
      const preferredVoice = voices.find(v => v.lang.includes('en-') && (v.name.includes('Google') || v.name.includes('Siri') || v.name.includes('Natural'))) 
                           || voices.find(v => v.lang.includes('en-'));
      if (preferredVoice) utterance.voice = preferredVoice;
      
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      
      utterance.onend = () => {
        if (currentSlide < slides.length - 1) {
          setCurrentSlide(prev => prev + 1);
        } else {
          setIsPlaying(false);
          setCurrentSlide(0); // Reset for replay
        }
      };

      synthRef.current.speak(utterance);
    }
  }, [currentSlide, isPlaying]);

  const togglePlay = () => {
    if (isPlaying) {
      synthRef.current.cancel();
      setIsPlaying(false);
    } else {
      // Resume or start
      if (currentSlide >= slides.length) setCurrentSlide(0);
      setIsPlaying(true);
    }
  };

  const handleClose = () => {
    if (synthRef.current) synthRef.current.cancel();
    onClose();
  };

  if (!memo) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-md p-4 font-sans animate-fade-in">
      <div 
        className="relative w-full max-w-sm rounded-[2rem] overflow-hidden shadow-2xl flex flex-col items-center justify-center text-white"
        style={{ 
          height: "85vh",
          maxHeight: "850px",
          background: "linear-gradient(135deg, #0f0c29, #302b63, #24243e)",
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255,255,255,0.1)"
        }}
      >
        {/* Ambient Animated Overlay */}
        <div className="absolute inset-0 opacity-30 mix-blend-overlay pointer-events-none" 
             style={{ backgroundImage: "radial-gradient(circle at 50% 50%, rgba(99, 102, 241, 0.4) 0%, transparent 50%)", animation: "pulse 4s infinite alternate" }}></div>
        
        {/* Header / Top Bar */}
        <div className="absolute top-0 left-0 right-0 p-6 flex justify-between items-center z-10 w-full bg-gradient-to-b from-black/60 to-transparent">
          <div className="flex gap-2 items-center">
            {isPlaying && (
              <div className="flex gap-1 items-end h-4">
                <div className="w-1 bg-green-400 rounded-full animate-[bounce_1s_infinite] h-full"></div>
                <div className="w-1 bg-green-400 rounded-full animate-[bounce_1s_infinite_0.2s] h-3/4"></div>
                <div className="w-1 bg-green-400 rounded-full animate-[bounce_1s_infinite_0.4s] h-full"></div>
              </div>
            )}
            <span className="text-xs font-bold uppercase tracking-widest text-gray-300">AI Video Brief</span>
          </div>
          <button 
            onClick={handleClose}
            className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center hover:bg-white/20 transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Play/Pause Center Indicator (shows briefly when toggled) */}
        {!isPlaying && currentSlide === 0 && (
          <div className="absolute inset-0 flex items-center justify-center z-20 pointer-events-none">
            <div className="w-20 h-20 rounded-full bg-white/10 backdrop-blur-md flex items-center justify-center pl-2 border border-white/20 animate-pulse">
              <div className="w-0 h-0 border-y-[12px] border-y-transparent border-l-[20px] border-l-white"></div>
            </div>
          </div>
        )}

        {/* Main Content Area (Click to toggle play) */}
        <div 
          className="relative z-10 w-full h-full flex flex-col justify-center px-8 cursor-pointer"
          onClick={togglePlay}
        >
          {slides[currentSlide] && slides[currentSlide].display}
        </div>

        {/* Progress Bar & Swipe Indicators */}
        <div className="absolute bottom-0 left-0 right-0 p-6 z-10 w-full bg-gradient-to-t from-black/80 to-transparent flex flex-col gap-4">
          <div className="flex gap-1 w-full">
            {slides.map((_, idx) => (
              <div 
                key={idx} 
                className="h-1 rounded-full flex-1 transition-all duration-300"
                style={{ 
                  background: idx < currentSlide ? "rgba(255,255,255,1)" : idx === currentSlide ? "rgba(255,255,255,0.8)" : "rgba(255,255,255,0.2)"
                }}
              ></div>
            ))}
          </div>
          <div className="flex justify-between items-center px-2">
            <span className="text-xs font-medium text-gray-400">{ticker}</span>
            <span className="text-xs font-medium text-gray-400">FinContext AI</span>
          </div>
        </div>

      </div>
    </div>
  );
}
