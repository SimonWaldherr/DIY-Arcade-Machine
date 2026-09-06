class HarborAdventureGame(FrameLoopGame):
    """A tiny original point-and-click mystery: Das Licht von Nebelhafen."""

    FRAME_MS = 35
    # id, label, inclusive hit rectangle. Scene art uses these same coordinates.
    HOTSPOTS = (
        (("crate", "KISTE", (3, 27, 15, 39)),
         ("rope", "SEIL", (20, 31, 29, 40)),
         ("grate", "GITTER", (34, 29, 45, 40)),
         ("inn", "ZUM WIRT", (2, 10, 20, 24)),
         ("tower", "ZUM TURM", (46, 8, 61, 25)),
         ("market", "ZUM MARKT", (25, 9, 42, 21))),
        (("keeper", "WIRT", (27, 16, 40, 33)),
         ("hook", "HAKEN", (47, 22, 57, 35)),
         ("harbor", "ZUM HAFEN", (2, 12, 15, 39))),
        (("lamp", "LAMPE", (25, 10, 40, 26)),
         ("crank", "KURBEL", (46, 29, 59, 40)),
         ("harbor", "ZUM HAFEN", (2, 20, 15, 40))),
    )
    # Optional routes form a loop, so every new scene has a visible way back.
    HOTSPOTS += (
        (("harbor", "ZUM HAFEN", (1, 27, 12, 42)),
         ("trader", "HAENDLER", (18, 13, 30, 28)),
         ("bread", "BROT", (17, 33, 27, 41)),
         ("oil", "OEL", (33, 33, 42, 41)),
         ("journal", "AUFTRAEGE", (35, 10, 47, 25)),
         ("beach", "ZUM STRAND", (51, 9, 62, 23)),
         ("workshop", "WERKSTATT", (50, 29, 62, 42))),
        (("market", "ZUM MARKT", (1, 27, 12, 42)),
         ("gull", "MOEWE", (22, 12, 36, 25)),
         ("bottle", "FLASCHE", (18, 32, 28, 42)),
         ("sand", "SAND", (36, 32, 47, 42)),
         ("workshop", "WERKSTATT", (51, 10, 62, 27))),
        (("market", "ZUM MARKT", (1, 27, 12, 42)),
         ("archive", "ZUM ARCHIV", (52, 8, 62, 22)),
         ("maker", "UHRMACHER", (18, 13, 30, 29)),
         ("clock", "UHR", (36, 9, 48, 27)),
         ("post", "POSTKASTEN", (34, 32, 46, 42)),
         ("beach", "ZUM STRAND", (52, 28, 62, 42))),
    )
    HOTSPOTS += (
        (("workshop", "WERKSTATT", (2, 28, 14, 42)),
         ("journal", "SEEKARTEN", (22, 17, 42, 33)),
         ("cliff", "ZUR KLIPPE", (50, 10, 62, 28))),
        (("archive", "ZUM ARCHIV", (2, 28, 14, 42)),
         ("view", "FERNROHR", (26, 16, 43, 34))),
    )
    ROUTES = {"harbor": 0, "inn": 1, "market": 3, "beach": 4, "workshop": 5, "archive": 6, "cliff": 7}
    ITEMS = ("MUENZE", "SEIL", "HAKEN", "ANKER", "LINSE", "SCHLUESSEL",
             "BROT", "GLOCKE", "BRIEF", "ZAHNRAD", "OEL", "LAUFRAD")
    ICONS = ("M", "S", "H", "A", "L", "K", "B", "G", "P", "Z", "O", "R")
    TITLES = ("NEBELHAFEN", "BEIM WIRT", "LEUCHTTURM", "MARKTPLATZ", "STRAND", "WERKSTATT", "SEEARCHIV", "KLIPPE")

    def __init__(self):
        self.reset()

    def reset(self):
        self.room = 0
        self.cursor_x, self.cursor_y = 32, 23
        self.inventory = []
        self.selected = None
        self.inventory_page = 0
        self.bread_found = False
        self.oil_found = False
        self.letter_found = False
        self.gear_found = False
        self.bell_found = False
        self.bell_returned = False
        self.letter_delivered = False
        self.clock_fixed = False
        self.coin_found = False
        self.rope_found = False
        self.hook_found = False
        self.key_found = False
        self.door_open = False
        self.lens_installed = False
        self.won = False
        self.score = 0
        self.pages = []
        self.page = 0
        self.choices = False
        self.choice = 0
        self.last_c = False
        self.last_z = True  # Do not carry the menu's confirmation into the story.
        self.last_pointer = None
        self.dirty = True
        self._say("Der Waerter ist fort. Sein letzter Brief: Bring das Licht zurueck!",
                  "Pfeile: Zeiger. Z: Aktion. X: Zurueck. Unten ist die Tasche. Mit > blaettern. Am Markt warten Nebenjobs.")

    def _say(self, *paragraphs):
        # Ten 5-pixel glyphs plus spacing fit the 64-pixel matrix.
        lines = []
        for paragraph in paragraphs:
            line = ""
            for word in paragraph.upper().split():
                if len(line) + len(word) + (1 if line else 0) > 10:
                    if line:
                        lines.append(line)
                    line = ""
                while len(word) > 10:
                    lines.append(word[:10])
                    word = word[10:]
                line = (line + " " + word) if line else word
            if line:
                lines.append(line)
        self.pages = [tuple(lines[i:i + 5]) for i in range(0, len(lines), 5)]
        self.page = 0
        self.dirty = True

    def _target(self):
        for target, unused_label, (x1, y1, x2, y2) in self.HOTSPOTS[self.room]:
            if x1 <= self.cursor_x <= x2 and y1 <= self.cursor_y <= y2:
                return target
        return None

    def _inventory_click(self, index):
        if index < 0 or index >= len(self.inventory):
            self.selected = None
            return
        item = self.inventory[index]
        if self.selected == item:
            self.selected = None
        elif ((self.selected == "SEIL" and item == "HAKEN") or
              (self.selected == "HAKEN" and item == "SEIL")):
            self.inventory.remove("SEIL")
            self.inventory.remove("HAKEN")
            self.inventory.append("ANKER")
            self.selected = "ANKER"
            self.score += 20
            self._say("Ein Haken am Seil. Mein erster Enteranker. Piraten waeren stolz.")
        elif ((self.selected == "OEL" and item == "ZAHNRAD") or
              (self.selected == "ZAHNRAD" and item == "OEL")):
            self.inventory.remove("OEL")
            self.inventory.remove("ZAHNRAD")
            self.inventory.append("LAUFRAD")
            self.selected = "LAUFRAD"
            self._say("Das Zahnrad laeuft wieder. Oel ist wie Tee fuer Maschinen.")
        else:
            self.selected = item
        self.dirty = True

    def _take(self, item, flag, text):
        if getattr(self, flag):
            self._say("Hier liegt nichts mehr.")
        else:
            setattr(self, flag, True)
            self.inventory.append(item)
            self.score += 10
            self._say(text)

    def _talk(self, choice):
        self.choices = False
        if choice == 0:
            self._say("WIRT: Der Waerter suchte ein Signal im Nebel. Dann blieb der Turm dunkel.",
                      "Sein Ersatz- schluessel fiel durchs Gitter am Kai. Sehr sicher, meinte er.")
        elif choice == 1:
            if "LINSE" in self.inventory or self.lens_installed:
                self._say("WIRT: Die Linse gehoert in die Lampe. Danach die Kurbel drehen!")
            elif "MUENZE" in self.inventory:
                self.inventory.remove("MUENZE")
                self.inventory.append("LINSE")
                self.selected = None
                self.score += 20
                self._say("WIRT: Eine Muenze? Nimm die Linse. Endlich ein Gast mit Durchblick.")
            else:
                self._say("WIRT: Die Linse kostet eine Muenze. Schau in die Kiste am Kai.")
        else:
            self._say("WIRT: Der Haken dort ist gratis. Das Seil liegt am Kai. Basteln hilft!")

    def _interact(self, target):
        # Only visible scene targets may be activated, including by tests/tools.
        if self.won or not any(target == h[0] for h in self.HOTSPOTS[self.room]):
            return
        if target in self.ROUTES:
            self.room = self.ROUTES[target]
            self.selected = None
        elif target == "tower":
            if self.door_open:
                self.room = 2
            elif self.selected == "SCHLUESSEL":
                self.door_open = True
                self.inventory.remove("SCHLUESSEL")
                self.selected = None
                self.score += 30
                self.room = 2
                self._say("Die Tuer ist offen. Die Lampe wartet auf eine neue Linse.")
            else:
                self._say("Verschlossen. Der Wirt weiss sicher mehr.")
        elif target == "crate":
            self._take("MUENZE", "coin_found", "Eine Muenze! Der Zoll hat wohl Feierabend.")
        elif target == "rope":
            self._take("SEIL", "rope_found", "Ein Seil. Fuer Knoten und andere Probleme.")
        elif target == "hook":
            self._take("HAKEN", "hook_found", "Ein Haken. Jetzt fehlt nur etwas Reichweite.")
        elif target == "grate":
            if self.key_found:
                self._say("Nur Wasser. Und mein Spiegelbild. Beide ratlos.")
            elif self.selected == "ANKER":
                self.inventory.remove("ANKER")
                self.selected = None
                self._take("SCHLUESSEL", "key_found", "Der Anker hebt den Schluessel! Das Seil reisst. Immerhin.")
            else:
                self._say("Ein Schluessel liegt tief unter dem Gitter. Mein Arm ist zu kurz.")
        elif target == "keeper":
            self.choices = True
            self.choice = 0
        elif target == "lamp":
            if self.lens_installed:
                self._say("Die Linse sitzt. Jetzt fehlt nur noch Energie.")
            elif self.selected == "LINSE":
                self.inventory.remove("LINSE")
                self.selected = None
                self.lens_installed = True
                self.score += 30
                self._say("Die Linse passt! Jetzt die Kurbel drehen.")
            else:
                self._say("Die Linse fehlt. Ohne sie bleibt das Signal unsichtbar.")
        elif target in ("bread", "oil", "bottle", "sand", "gull", "trader", "maker", "clock", "post", "journal"):
            self._side_quest(target)
        elif target == "view":
            self._say("Ein Schiff im Nebel. An Deck steht jemand mit einer Teetasse. Das Licht im Turm koennte ihn erreichen.")
        elif target == "crank":
            if self.lens_installed:
                self.won = True
                self.score += 100
                self._say("Licht teilt den Nebel. Ein Schiff antwortet: BIN AN BORD. TEE IST GUT.",
                          "Der Waerter lebt! Sein Brief war wohl eine Urlaubs- vertretung.",
                          "Nebenjobs: %d von 3 erledigt." % self._quest_count(),
                          "NEBELHAFEN ist gerettet. Und ich brauche Urlaub. ENDE.")
            else:
                self._say("Es knistert. Ohne Linse streut das Licht ins Leere.")
        self.dirty = True

    def _quest_count(self):
        return int(self.bell_returned) + int(self.letter_delivered) + int(self.clock_fixed)

    def _complete_quest(self, flag, item, text):
        if getattr(self, flag):
            self._say("Schon erledigt. Dein guter Ruf bleibt!")
        elif self.selected == item and item in self.inventory:
            self.inventory.remove(item)
            self.selected = None
            setattr(self, flag, True)
            self.score += 50
            self._say(text)
        else:
            return False
        return True

    def _side_quest(self, target):
        if target == "bread":
            self._take("BROT", "bread_found", "Gratis Brot von gestern. Fuer Menschen hart. Fuer Moewen Luxus.")
        elif target == "oil":
            self._take("OEL", "oil_found", "Eine Probe Uhrenoel. Bitte nicht als Salatoel nutzen.")
        elif target == "bottle":
            self._take("BRIEF", "letter_found", "Flaschenpost! AN DEN UHRMACHER. Bitte in seinen Postkasten werfen.")
        elif target == "sand":
            self._take("ZAHNRAD", "gear_found", "Ein rostiges Zahnrad. Oel koennte helfen. Die Werkstatt ist gleich dort.")
        elif target == "gull":
            if self.bell_found:
                self._say("Die Moewe kaut zufrieden. Sie nimmt keine weiteren Auftraege an.")
            elif self.selected == "BROT":
                self.inventory.remove("BROT")
                self.selected = None
                self._take("GLOCKE", "bell_found", "Brot gegen Glocke. Die Moewe ist die beste Haendlerin am Strand.")
            else:
                self._say("Eine Moewe bewacht eine Glocke. Ihr Blick sagt: Erst Brot, dann Handel.")
        elif target == "trader":
            if not self._complete_quest("bell_returned", "GLOCKE",
                    "Meine Marktglocke! Du bist nun EHRENKUNDE. Leider ohne Rabatt. +50 Punkte."):
                self._say("Die Moewe am Strand hat meine Glocke! Am Brotstand gibt es eine Gratisprobe.")
        elif target == "post":
            if not self._complete_quest("letter_delivered", "BRIEF",
                    "Brief zugestellt! Der Uhrmacher liest: Bin auf See. Deine Schwester. Er laechelt. +50 Punkte."):
                self._say("Post fuer den Uhrmacher. Er wartet auf einen Brief vom Meer. Such am Strand.")
        elif target == "clock":
            if not self._complete_quest("clock_fixed", "LAUFRAD",
                    "Tick. Tack! Die Uhr geht wieder. Du bist EHRENMECHANIKER. +50 Punkte."):
                self._say("Ein Zahnrad fehlt. Ein rostiges passt nicht. Suche am Strand und am Oelstand.")
        elif target == "maker":
            if self.clock_fixed and self.letter_delivered:
                self._say("Uhr und Herz ticken wieder. Danke! Der Waerter schuldet mir noch Urlaub.")
            elif self.clock_fixed:
                self._say("Die Uhr laeuft! Nun fehlt nur Post von meiner Schwester. Schau am Strand.")
            else:
                self._say("Mein Zahnrad fiel am Strand in den Sand. Oele es und setze es in die Uhr.",
                          "Ich warte auch auf Post. Mein Kasten ist dort unten.")
        elif target == "journal":
            self._say("NEBENJOBS %d VON 3" % self._quest_count(),
                      "GLOCKE: " + ("Erledigt." if self.bell_returned else "Brot zur Moewe. Glocke zum Haendler."),
                      "POST: " + ("Erledigt." if self.letter_delivered else "Flasche am Strand suchen. Brief zum Postkasten."),
                      "UHR: " + ("Erledigt." if self.clock_fixed else "Zahnrad im Sand. Mit Oel mischen. In Uhr setzen."),
                      "Alles freiwillig. Die Kurbel im Leuchtturm beendet die Reise.")

    def _inventory_pages(self):
        return max(1, (len(self.inventory) + 3) // 4)

    def _activate(self):
        if self.pages:
            self.page += 1
            if self.page >= len(self.pages):
                self.pages = []
                self.page = 0
        elif self.choices:
            self._talk(self.choice)
        elif self.cursor_y >= 46:
            self.inventory_page %= self._inventory_pages()
            if self.cursor_x >= 52:
                self.inventory_page = (self.inventory_page + 1) % self._inventory_pages()
            else:
                self._inventory_click(self.inventory_page * 4 + self.cursor_x // 13)
        else:
            target = self._target()
            if target:
                self._interact(target)
        self.dirty = True

    def _read_pointer(self):
        pg = getattr(display, "_pg", None)
        screen = getattr(display, "_screen", None)
        if pg is None or screen is None:
            return False
        clicked = False
        position = pg.mouse.get_pos()
        for event in pg.event.get([pg.MOUSEBUTTONDOWN]):
            if event.button == 1:
                position = event.pos
                clicked = True
        if position != self.last_pointer or clicked:
            # Respect joystick movement until the mouse actually moves again.
            if self.last_pointer is not None or clicked:
                w, h = screen.get_size()
                self.cursor_x = clamp(position[0] * WIDTH // w, 0, 63)
                self.cursor_y = clamp(position[1] * HEIGHT // h, 7, 55)
                if self.choices:
                    self.choice = clamp((self.cursor_y - 15) // 10, 0, 2)
                self.dirty = True
            self.last_pointer = position
        return clicked

    @staticmethod
    def _draw_arrow(x, y, left=False):
        # The compact runtime font has no < or > glyphs.
        draw_rectangle(x, y + 2, x + 5, y + 2, 245, 220, 140)
        tip = x if left else x + 5
        direction = 1 if left else -1
        for offset in (1, 2):
            display.set_pixel(tip + direction * offset, y + 2 - offset, 245, 220, 140)
            display.set_pixel(tip + direction * offset, y + 2 + offset, 245, 220, 140)

    def _draw_scene(self):
        draw_rectangle(0, 7, 63, 43, 14, 24, 42)
        if self.room == 0:
            draw_rectangle(0, 32, 63, 43, 25, 75, 105)
            for x in range(1, 64, 9):
                draw_rectangle(x, 41, x + 4, 41, 65, 135, 160)
            draw_rectangle(27, 9, 40, 19, 125, 95, 60)
            self._draw_arrow(29, 11)
            draw_rectangle(0, 25, 32, 43, 90, 65, 45)
            draw_rectangle(2, 10, 20, 24, 135, 85, 60)
            draw_rectangle(7, 16, 14, 24, 40, 25, 30)
            draw_rectangle(46, 8, 61, 25, 130, 145, 155)
            draw_rectangle(49, 10, 58, 13, 240, 195, 80)
            draw_rectangle(51, 19, 56, 25, 30, 35, 45)
            draw_rectangle(3, 27, 15, 39, 155, 105, 45)
            draw_rect_outline(4, 28, 14, 38, 225, 165, 75)
            if not self.rope_found:
                draw_rect_outline(21, 32, 28, 39, 210, 180, 95)
            draw_rectangle(34, 29, 45, 40, 12, 20, 25)
            for x in range(35, 46, 3):
                draw_rectangle(x, 29, x, 40, 110, 125, 135)
            if not self.key_found:
                display.set_pixel(39, 36, 255, 210, 50)
        elif self.room == 1:
            draw_rectangle(17, 8, 63, 43, 75, 40, 35)
            draw_rectangle(2, 12, 15, 39, 25, 65, 100)
            draw_rectangle(27, 16, 40, 33, 55, 130, 110)
            draw_rectangle(30, 13, 37, 21, 235, 170, 110)
            display.set_pixel(32, 16, 20, 20, 25)
            display.set_pixel(36, 16, 20, 20, 25)
            draw_rectangle(20, 34, 62, 40, 155, 100, 50)
            if not self.hook_found:
                draw_rectangle(52, 22, 53, 32, 185, 200, 215)
                draw_rectangle(48, 31, 53, 33, 185, 200, 215)
                display.set_pixel(48, 30, 185, 200, 215)
        elif self.room == 2:
            draw_rectangle(17, 7, 63, 43, 65, 70, 80)
            draw_rectangle(2, 20, 15, 40, 25, 65, 100)
            draw_rectangle(25, 10, 40, 26, 150, 140, 80)
            color = (100, 225, 240) if self.lens_installed else (20, 25, 35)
            draw_rectangle(28, 13, 37, 23, *color)
            draw_rectangle(30, 27, 35, 42, 120, 125, 140)
            draw_rectangle(46, 32, 56, 34, 210, 170, 70)
            draw_rectangle(55, 29, 58, 40, 210, 170, 70)

        elif self.room == 3:
            draw_rectangle(0, 7, 63, 43, 70, 60, 65)
            draw_rectangle(15, 10, 32, 14, 195, 70, 65)
            draw_rectangle(21, 15, 27, 21, 225, 165, 110)
            draw_rectangle(18, 22, 30, 28, 70, 145, 95)
            draw_rectangle(15, 31, 44, 42, 120, 80, 45)
            if not self.bread_found:
                draw_rectangle(18, 35, 25, 39, 230, 180, 90)
            if not self.oil_found:
                draw_rectangle(36, 34, 39, 40, 120, 205, 145)
            draw_rectangle(35, 10, 47, 25, 205, 185, 135)
            for y in (13, 17, 21):
                draw_rectangle(38, y, 44, y, 70, 60, 50)
            if self.bell_returned:
                draw_rectangle(29, 17, 31, 20, 255, 215, 60)
        elif self.room == 4:
            draw_rectangle(0, 7, 63, 28, 40, 110, 150)
            draw_rectangle(0, 29, 63, 43, 195, 165, 105)
            for x in range(2, 64, 9):
                draw_rectangle(x, 27, x + 4, 27, 155, 220, 235)
            draw_rectangle(26, 18, 34, 22, 235, 240, 230)
            draw_rectangle(23, 15, 27, 19, 235, 240, 230)
            display.set_pixel(24, 16, 15, 25, 30)
            display.set_pixel(22, 18, 255, 180, 60)
            if not self.bell_found:
                draw_rectangle(30, 23, 33, 25, 255, 215, 60)
            if not self.letter_found:
                draw_rectangle(21, 34, 24, 41, 65, 155, 110)
            if not self.gear_found:
                draw_rect_outline(39, 35, 44, 40, 130, 85, 45)
        elif self.room == 5:
            draw_rectangle(0, 7, 63, 43, 65, 50, 45)
            draw_rectangle(18, 22, 30, 29, 95, 125, 175)
            draw_rectangle(21, 14, 27, 21, 225, 170, 120)
            draw_rectangle(16, 30, 49, 32, 130, 90, 60)
            draw_rectangle(36, 9, 48, 27, 160, 115, 65)
            draw_rectangle(38, 11, 46, 21, 235, 225, 180)
            draw_rectangle(42, 13, 42, 17, 35, 45, 60)
            draw_rectangle(42, 17, 45, 17, 35, 45, 60)
            display.set_pixel(42, 24, *( (90, 245, 130) if self.clock_fixed else (245, 80, 65)))
            draw_rectangle(34, 34, 46, 42, 65, 105, 165)
            draw_rectangle(36, 36, 44, 36, 10, 20, 35)
            if self.letter_delivered:
                draw_rectangle(38, 39, 42, 40, 245, 225, 160)
        elif self.room == 6:
            draw_rectangle(16, 8, 46, 42, 90, 55, 35)
            for y in (10, 18, 26):
                draw_rectangle(18, y, 45, y + 1, 175, 120, 65)
            draw_rectangle(22, 19, 42, 33, 220, 200, 145)
            draw_rectangle(25, 23, 38, 24, 65, 115, 130)
            draw_rectangle(35, 23, 36, 30, 65, 115, 130)
        elif self.room == 7:
            draw_rectangle(0, 7, 63, 29, 50, 80, 120)
            draw_rectangle(0, 30, 63, 43, 35, 90, 135)
            draw_rectangle(18, 32, 49, 43, 95, 100, 90)
            draw_rectangle(28, 18, 43, 22, 210, 170, 85)
            draw_rectangle(33, 23, 35, 34, 135, 125, 105)
            draw_rectangle(52, 29, 59, 30, 220, 200, 165)
        if self.room >= 3:
            for target, unused_label, (x1, y1, x2, y2) in self.HOTSPOTS[self.room]:
                if target in self.ROUTES:
                    draw_rectangle(x1, y1, x2, y2, 30, 55, 70)
                    self._draw_arrow(x1 + 2, y1 + 4, target in ("market", "harbor"))

    def _draw(self):
        if self.dirty:
            display.clear()
            self._draw_scene()
            label = self.TITLES[self.room]
            for target, name, unused_box in self.HOTSPOTS[self.room]:
                if target == self._target():
                    label = name
            self.inventory_page %= self._inventory_pages()
            if self.selected:
                label = self.selected
            if self.cursor_y >= 46:
                slot = self.inventory_page * 4 + self.cursor_x // 13
                if self.cursor_x >= 52:
                    label = "TASCHE %d/%d" % (self.inventory_page + 1, self._inventory_pages())
                elif slot < len(self.inventory):
                    label = self.inventory[slot]
            draw_text_small(2, 0, label, 245, 225, 160)
            for index, item in enumerate(self.inventory[self.inventory_page * 4:self.inventory_page * 4 + 4]):
                x = index * 13
                color = (255, 210, 65) if item == self.selected else (85, 115, 145)
                draw_rect_outline(x, 46, min(63, x + 11), 55, *color)
                draw_text_small(x + 3, 48, self.ICONS[self.ITEMS.index(item)], *color)
            draw_rect_outline(52, 46, 63, 55, 150, 140, 90)
            self._draw_arrow(55, 48)
            if self.pages or self.choices:
                draw_rectangle(0, 7, 63, 56, 8, 12, 25)
                if self.pages:
                    for index, line in enumerate(self.pages[self.page]):
                        draw_text_small(2, 10 + index * 8, line, 230, 235, 245)
                    draw_text_small(2, 51, "Z: WEITER", 245, 200, 75)
                else:
                    for index, line in enumerate(("WAERTER?", "LINSE?", "TIPP?")):
                        color = (255, 215, 75) if index == self.choice else (160, 180, 205)
                        draw_text_small(2, 15 + index * 10, line, *color)
                    draw_text_small(2, 49, "Z: FRAGEN", 245, 200, 75)
            else:
                x, y = self.cursor_x, self.cursor_y
                draw_rectangle(max(0, x - 2), y, min(63, x + 2), y, 255, 255, 255)
                draw_rectangle(x, max(7, y - 2), x, min(55, y + 2), 255, 255, 255)
            self.dirty = False
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            cancel = c_button and not self.last_c
            self.last_c = c_button
            if cancel:
                if self.pages:
                    self.pages = []
                elif self.choices:
                    self.choices = False
                elif self.selected:
                    self.selected = None
                else:
                    return False
                self.dirty = True
            clicked = self._read_pointer()
            direction = joystick.read_direction(JOYSTICK_DIRECTIONS_4)
            dx, dy = direction_to_delta(direction)
            if self.choices and dy:
                self.choice = (self.choice + dy) % 3
                self.dirty = True
            elif not self.pages and (dx or dy):
                self.cursor_x = clamp(self.cursor_x + dx * 3, 0, 63)
                self.cursor_y = clamp(self.cursor_y + dy * 3, 7, 55)
                self.dirty = True
            if clicked or (z_button and not self.last_z):
                self._activate()
            self.last_z = z_button
            self._draw()
            if self.won and not self.pages:
                set_game_over_score(self.score, won=True)
                return False
            return True

        return step


