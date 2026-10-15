"""
Transformer architecture explained with Manim Community Edition.

Install:   pip install manim
Render:    manim -pql transformer_manim.py TransformerExplained
Higher quality: manim -pqh transformer_manim.py TransformerExplained

Example sentence used throughout: "The cat sat"
"""

from manim import *
import numpy as np

SENTENCE = ["The", "cat", "sat"]
COLORS = [BLUE, GREEN, ORANGE]


def token_boxes(words, colors, y=0.0, width=1.6, height=0.7, spacing=2.2):
    """Return a VGroup of labeled rounded boxes, one per token."""
    group = VGroup()
    n = len(words)
    for i, (w, c) in enumerate(zip(words, colors)):
        box = RoundedRectangle(
            corner_radius=0.1, width=width, height=height,
            color=c, fill_color=c, fill_opacity=0.25,
        )
        label = Text(w, font_size=26).move_to(box)
        item = VGroup(box, label)
        item.move_to(RIGHT * (i - (n - 1) / 2) * spacing + UP * y)
        group.add(item)
    return group


def vector_bar(color, n=4, width=0.25, height=0.18):
    """A small column of squares that stands for an embedding vector."""
    squares = VGroup(*[
        Square(side_length=height, color=color, fill_color=color,
               fill_opacity=np.random.uniform(0.2, 0.9), stroke_width=1)
        for _ in range(n)
    ]).arrange(DOWN, buff=0.02)
    return squares


class TransformerExplained(Scene):
    def construct(self):
        np.random.seed(3)
        self.intro()
        self.step_tokens_and_embeddings()
        self.step_positional_encoding()
        self.step_self_attention()
        self.step_multi_head_and_ffn()
        self.step_full_architecture()
        self.outro()

    # ------------------------------------------------------------------
    def title_card(self, text, sub=None):
        t = Text(text, font_size=36, weight=BOLD).to_edge(UP)
        group = VGroup(t)
        if sub:
            s = Text(sub, font_size=22, color=GRAY_B).next_to(t, DOWN, buff=0.15)
            group.add(s)
        return group

    def intro(self):
        title = Text("The Transformer", font_size=60, weight=BOLD)
        sub = Text("Attention Is All You Need (2017)", font_size=28, color=GRAY_B)
        sub.next_to(title, DOWN)
        self.play(Write(title), FadeIn(sub, shift=UP))
        self.wait(1.5)
        self.play(FadeOut(title), FadeOut(sub))

    # ------------------------------------------------------------------
    def step_tokens_and_embeddings(self):
        header = self.title_card("Step 1: Tokens to embeddings",
                                 "Each word becomes a vector of numbers")
        self.play(FadeIn(header))

        tokens = token_boxes(SENTENCE, COLORS, y=1.2)
        self.play(LaggedStart(*[FadeIn(t, shift=DOWN) for t in tokens],
                              lag_ratio=0.3))

        arrows = VGroup(*[Arrow(t.get_bottom(), t.get_bottom() + DOWN * 1.0,
                                buff=0.1, color=GRAY) for t in tokens])
        emb_label = Text("Embedding lookup", font_size=20, color=GRAY_B)
        emb_label.next_to(arrows, RIGHT, buff=0.4).shift(RIGHT * 1.2)
        vectors = VGroup(*[
            vector_bar(c, n=6).next_to(a, DOWN, buff=0.1)
            for a, c in zip(arrows, COLORS)
        ])
        self.play(LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.2),
                  FadeIn(emb_label))
        self.play(LaggedStart(*[FadeIn(v, scale=0.5) for v in vectors],
                              lag_ratio=0.2))

        note = Text("Real models use 512 or more numbers per word.",
                    font_size=22, color=YELLOW).to_edge(DOWN)
        self.play(Write(note))
        self.wait(2)

        self.embeddings = vectors
        self.tokens = tokens
        self.play(FadeOut(header), FadeOut(arrows), FadeOut(emb_label),
                  FadeOut(note))

    # ------------------------------------------------------------------
    def step_positional_encoding(self):
        header = self.title_card("Step 2: Positional encoding",
                                 "Attention has no sense of order, so we add position")
        self.play(FadeIn(header))

        pos_labels = VGroup(*[
            Text(f"pos {i}", font_size=20, color=YELLOW)
            .next_to(v, DOWN, buff=0.35)
            for i, v in enumerate(self.embeddings)
        ])
        plus = VGroup(*[
            MathTex("+", color=YELLOW).scale(0.9).next_to(v, DOWN, buff=0.05)
            for v in self.embeddings
        ])
        pos_vecs = VGroup(*[
            vector_bar(YELLOW, n=6).move_to(p).shift(DOWN * 0.1)
            for p in pos_labels
        ])
        self.play(LaggedStart(*[FadeIn(p, shift=UP) for p in pos_vecs],
                              lag_ratio=0.2), FadeIn(pos_labels))
        self.wait(1)

        merged = VGroup(*[
            vector_bar(c, n=6).move_to(v) for v, c in zip(self.embeddings, COLORS)
        ])
        self.play(
            *[Transform(self.embeddings[i], merged[i]) for i in range(3)],
            FadeOut(pos_vecs), FadeOut(pos_labels),
        )

        note = Text("Word vector + position vector = input to the first layer",
                    font_size=22, color=YELLOW).to_edge(DOWN)
        self.play(Write(note))
        self.wait(2)
        self.play(FadeOut(header), FadeOut(note), FadeOut(plus))

    # ------------------------------------------------------------------
    def step_self_attention(self):
        header = self.title_card("Step 3: Self-attention",
                                 "Every word looks at every other word")
        self.play(FadeIn(header))

        # Move tokens/vectors up a bit to make room
        stack = VGroup(self.tokens, self.embeddings)
        self.play(stack.animate.shift(UP * 0.2))

        # Query / Key / Value explanation
        qkv = VGroup(
            MathTex(r"Q = XW_Q", color=RED),
            MathTex(r"K = XW_K", color=BLUE),
            MathTex(r"V = XW_V", color=GREEN),
        ).arrange(RIGHT, buff=1.0).scale(0.9).to_edge(DOWN, buff=1.6)
        legend = VGroup(
            Text("Q: what am I looking for?", font_size=18, color=RED),
            Text("K: what do I contain?", font_size=18, color=BLUE),
            Text("V: what do I pass along?", font_size=18, color=GREEN),
        )
        for l, f in zip(legend, qkv):
            l.next_to(f, DOWN, buff=0.15)
        self.play(LaggedStart(*[Write(f) for f in qkv], lag_ratio=0.3))
        self.play(LaggedStart(*[FadeIn(l) for l in legend], lag_ratio=0.3))
        self.wait(2)
        self.play(FadeOut(qkv), FadeOut(legend))

        # Attention arrows from "sat" to the others, thickness = weight
        sat = self.tokens[2]
        weights = [0.25, 0.60, 0.15]  # sat attends to The, cat, sat
        arcs = VGroup()
        wl = VGroup()
        for i, w in enumerate(weights):
            tgt = self.tokens[i]
            if i == 2:
                arc = Arc(radius=0.6, start_angle=0, angle=TAU * 0.85,
                          color=ORANGE).scale(0.7).next_to(sat, UP, buff=0.05)
                arc.set_stroke(width=2 + 10 * w)
            else:
                arc = CurvedArrow(sat.get_top() + UP * 0.05,
                                  tgt.get_top() + UP * 0.05,
                                  angle=TAU / 5 if i == 1 else TAU / 3.2,
                                  color=ORANGE)
                arc.set_stroke(width=2 + 10 * w)
            arcs.add(arc)
            lab = Text(f"{w:.2f}", font_size=22, color=ORANGE)
            lab.move_to(arc.get_center() + UP * 0.35)
            wl.add(lab)
        self.play(LaggedStart(*[Create(a) for a in arcs], lag_ratio=0.3))
        self.play(FadeIn(wl))

        caption = Text('"sat" pays most attention to "cat" (who is sitting)',
                       font_size=22, color=ORANGE).to_edge(DOWN, buff=1.4)
        formula = MathTex(
            r"\text{Attention}(Q,K,V)=\text{softmax}\!\left(\frac{QK^T}{\sqrt{d_k}}\right)V"
        ).scale(0.85).to_edge(DOWN, buff=0.5)
        self.play(Write(caption))
        self.play(Write(formula))
        self.wait(3)

        self.play(FadeOut(arcs), FadeOut(wl), FadeOut(caption),
                  FadeOut(formula), FadeOut(header))
        self.play(stack.animate.shift(DOWN * 0.2))

    # ------------------------------------------------------------------
    def step_multi_head_and_ffn(self):
        self.play(FadeOut(self.tokens), FadeOut(self.embeddings))
        header = self.title_card("Step 4: Multi-head attention, add and norm, feed-forward",
                                 "One encoder layer, built from small pieces")
        self.play(FadeIn(header))

        def block(text, color, w=4.2, h=0.7):
            r = RoundedRectangle(corner_radius=0.1, width=w, height=h,
                                 color=color, fill_color=color, fill_opacity=0.25)
            t = Text(text, font_size=22).move_to(r)
            return VGroup(r, t)

        heads = VGroup(*[
            block(f"Head {i+1}", [RED, BLUE, GREEN][i], w=1.3, h=0.6)
            for i in range(3)
        ]).arrange(RIGHT, buff=0.2)
        concat = block("Concat + linear", PURPLE, w=4.2)
        addnorm1 = block("Add and LayerNorm", GRAY, w=4.2)
        ffn = block("Feed-forward network", TEAL, w=4.2)
        addnorm2 = block("Add and LayerNorm", GRAY, w=4.2)

        col = VGroup(heads, concat, addnorm1, ffn, addnorm2).arrange(UP, buff=0.35)
        col.next_to(header, DOWN, buff=0.4).shift(LEFT * 2.5)
        # arrange(UP) stacks bottom-to-top, so heads sit at the bottom.
        col.move_to(LEFT * 2.5 + DOWN * 0.4)

        arrows = VGroup(*[
            Arrow(a.get_top(), b.get_bottom(), buff=0.05, stroke_width=3,
                  max_tip_length_to_length_ratio=0.3, color=GRAY)
            for a, b in zip(col[:-1], col[1:])
        ])

        notes = VGroup(
            Text("Several heads attend in parallel,\neach learns a different relation.", font_size=20),
            Text("Heads are joined and mixed\nwith one linear layer.", font_size=20),
            Text("Residual connection keeps the input,\nnorm keeps values stable.", font_size=20),
            Text("Two linear layers with ReLU,\napplied to each word separately.", font_size=20),
            Text("Same add and norm again.", font_size=20),
        )
        for n, b in zip(notes, col):
            n.next_to(b, RIGHT, buff=0.5).set_x(3.2, direction=LEFT)
            n.set_color(GRAY_B)

        for i in range(5):
            anims = [FadeIn(col[i], shift=UP * 0.2), FadeIn(notes[i])]
            if i > 0:
                anims.append(GrowArrow(arrows[i - 1]))
            self.play(*anims, run_time=0.8)
            self.wait(0.6)

        # Residual skip arrows
        skip1 = CurvedArrow(heads.get_left() + LEFT * 0.1,
                            addnorm1.get_left() + LEFT * 0.1,
                            angle=-TAU / 4, color=YELLOW, stroke_width=3)
        skip2 = CurvedArrow(addnorm1.get_left() + LEFT * 0.1,
                            addnorm2.get_left() + LEFT * 0.1,
                            angle=-TAU / 4, color=YELLOW, stroke_width=3)
        skip_lbl = Text("skip connections", font_size=18, color=YELLOW)
        skip_lbl.next_to(skip1, LEFT, buff=0.1)
        self.play(Create(skip1), Create(skip2), FadeIn(skip_lbl))
        self.wait(2.5)

        self.play(*[FadeOut(m) for m in
                    [header, col, arrows, notes, skip1, skip2, skip_lbl]])

    # ------------------------------------------------------------------
    def step_full_architecture(self):
        header = self.title_card("Step 5: The full architecture",
                                 "Encoder on the left, decoder on the right")
        self.play(FadeIn(header))

        def block(text, color, w=3.0, h=0.55, fs=18):
            r = RoundedRectangle(corner_radius=0.08, width=w, height=h,
                                 color=color, fill_color=color, fill_opacity=0.25)
            t = Text(text, font_size=fs).move_to(r)
            return VGroup(r, t)

        # Encoder column
        enc_in = block("Input embedding + position", YELLOW)
        enc_att = block("Multi-head self-attention", BLUE)
        enc_ff = block("Feed-forward", TEAL)
        enc = VGroup(enc_in, enc_att, enc_ff).arrange(UP, buff=0.35)
        enc_box = SurroundingRectangle(VGroup(enc_att, enc_ff), color=BLUE,
                                       buff=0.2, corner_radius=0.1)
        enc_nx = Text("N x", font_size=22, color=BLUE).next_to(enc_box, LEFT, buff=0.1)
        enc_title = Text("Encoder", font_size=26, color=BLUE)

        # Decoder column
        dec_in = block("Output embedding + position", YELLOW)
        dec_masked = block("Masked self-attention", RED)
        dec_cross = block("Cross-attention", PURPLE)
        dec_ff = block("Feed-forward", TEAL)
        dec = VGroup(dec_in, dec_masked, dec_cross, dec_ff).arrange(UP, buff=0.35)
        dec_box = SurroundingRectangle(VGroup(dec_masked, dec_cross, dec_ff),
                                       color=RED, buff=0.2, corner_radius=0.1)
        dec_nx = Text("N x", font_size=22, color=RED).next_to(dec_box, RIGHT, buff=0.1)
        dec_title = Text("Decoder", font_size=26, color=RED)

        top_lin = block("Linear + Softmax", GREEN)
        out_lbl = Text("Next word probabilities", font_size=18, color=GREEN)

        enc_group = VGroup(enc, enc_box, enc_nx)
        dec_group = VGroup(dec, dec_box, dec_nx)
        enc_group.move_to(LEFT * 3.3 + DOWN * 0.5)
        dec_group.move_to(RIGHT * 3.3 + DOWN * 0.5)
        enc_title.next_to(enc_box, UP, buff=0.2)
        dec_title.next_to(dec_box, UP, buff=0.2)
        top_lin.next_to(dec_title, UP, buff=0.15)
        out_lbl.next_to(top_lin, UP, buff=0.1)

        self.play(FadeIn(enc_group, shift=UP), FadeIn(enc_title))
        self.wait(0.5)
        self.play(FadeIn(dec_group, shift=UP), FadeIn(dec_title))

        # Cross-attention link: encoder output feeds the decoder
        link = Arrow(enc_box.get_right(), dec_cross.get_left(),
                     buff=0.1, color=PURPLE, stroke_width=4)
        link_lbl = Text("keys and values", font_size=16, color=PURPLE)
        link_lbl.next_to(link, UP, buff=0.05)
        self.play(GrowArrow(link), FadeIn(link_lbl))
        self.wait(1)
        self.play(FadeIn(top_lin), FadeIn(out_lbl))
        self.wait(1)

        notes = Text(
            "GPT uses only the decoder. BERT uses only the encoder.",
            font_size=22, color=YELLOW,
        ).to_edge(DOWN, buff=0.3)
        self.play(Write(notes))
        self.wait(3)

        self.play(*[FadeOut(m) for m in self.mobjects])

    # ------------------------------------------------------------------
    def outro(self):
        recap = VGroup(
            Text("1. Turn words into vectors", font_size=30),
            Text("2. Add position information", font_size=30),
            Text("3. Let words attend to each other", font_size=30),
            Text("4. Process each word with a feed-forward net", font_size=30),
            Text("5. Stack layers, then predict the next word", font_size=30),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.4)
        title = Text("Recap", font_size=44, weight=BOLD).to_edge(UP)
        self.play(Write(title))
        self.play(LaggedStart(*[FadeIn(r, shift=RIGHT) for r in recap],
                              lag_ratio=0.5))
        self.wait(3)
        self.play(FadeOut(recap), FadeOut(title))