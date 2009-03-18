#!/usr/bin/env python
#
#       pympress
#
#       Copyright 2009 Thomas Jost <thomas.jost@gmail.com>
#
#       This program is free software; you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation; either version 2 of the License, or
#       (at your option) any later version.
#
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
#
#       You should have received a copy of the GNU General Public License
#       along with this program; if not, write to the Free Software
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#       MA 02110-1301, USA.

import cairo
import gobject
import gtk
import pango
import os.path
import poppler
import sys
import time

class Document:
	def __init__(self, uri, page=0):
		# Open PDF file
		self.doc = poppler.document_new_from_file(uri, None)

		# Pages number
		self.nb_pages = self.doc.get_n_pages()

		# Open first two pages
		self.current, first, second = self.get_current_and_next(page)

		# Create windows
		self.presenter = Presenter(first, second, self.current, self.nb_pages, self.event_callback)
		self.content = Content(first, self.event_callback)

	def get_current_and_next(self, page):
		if page >= self.nb_pages:
			page = self.nb_pages-1
		elif page < 0:
			page = 0
		current = self.doc.get_page(page)

		next = None
		if page+1 < self.nb_pages:
			next = self.doc.get_page(page+1)

		return (page, current, next)

	def run(self):
		gtk.main()

	def next(self):
		page, current, next = self.get_current_and_next(self.current + 1)
		self.content.set_page(current)
		self.presenter.set_page(current, next, page)
		self.current = page

	def prev(self):
		page, current, next = self.get_current_and_next(self.current - 1)
		self.content.set_page(current)
		self.presenter.set_page(current, next, page)
		self.current = page

	def fullscreen(self):
		self.content.switch_fullscreen()

	def event_callback(self, widget, event):
		if event.type == gtk.gdk.KEY_PRESS:
			name = gtk.gdk.keyval_name(event.keyval)

			if name in ["Right", "Down", "Page_Down", "space"]:
				self.next()
			elif name in ["Left", "Up", "Page_Up", "BackSpace"]:
				self.prev()
			elif (name.upper() in ["F", "F11"]) \
				or (name == "Return" and event.state & gtk.gdk.MOD1_MASK) \
				or (name.upper() == "L" and event.state & gtk.gdk.CONTROL_MASK):
				self.fullscreen()
			elif name.upper() == "Q":
				gtk.main_quit()

		elif event.type == gtk.gdk.BUTTON_PRESS:
			if event.button == 1:
				self.next()
			else:
				self.prev()

		elif event.type == gtk.gdk.SCROLL:
			if event.direction in [gtk.gdk.SCROLL_RIGHT, gtk.gdk.SCROLL_DOWN]:
				self.next()
			else:
				self.prev()

		else:
			print "Unknown event %s" % event.type

class Content:
	def __init__(self, page, event_callback):
		black = gtk.gdk.Color(0, 0, 0)

		# Main window
		self.win = gtk.Window(gtk.WINDOW_TOPLEVEL)
		self.win.set_title("pympress content")
		self.win.set_default_size(800, 600)
		self.win.modify_bg(gtk.STATE_NORMAL, black)
		self.win.connect("delete-event", gtk.main_quit)

		# Aspect frame
		self.frame = gtk.AspectFrame(ratio=4./3., obey_child=False)
		self.frame.modify_bg(gtk.STATE_NORMAL, black)

		# Drawing area
		self.da = gtk.DrawingArea()
		self.da.modify_bg(gtk.STATE_NORMAL, black)
		self.da.connect("expose-event", self.on_expose)

		# Prepare the window
		self.frame.add(self.da)
		self.win.add(self.frame)
		self.win.add_events(gtk.gdk.KEY_PRESS_MASK | gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.SCROLL_MASK)
		self.win.connect("key-press-event", event_callback)
		self.win.connect("button-press-event", event_callback)
		self.win.connect("scroll-event", event_callback)

		# Don't start in fullscreen mode
		self.fullscreen = False

		# Add the page
		self.set_page(page)

		self.win.show_all()

	def set_page(self, page):
		self.page = page

		# Page size
		self.pw, self.ph = self.page.get_size()

		# Page aspect ratio
		pr = self.pw / self.ph
		self.frame.set_property("ratio", pr)

		# Don't queue draw event but draw directly (faster)
		self.on_expose(self.da)

	def switch_fullscreen(self):
		if self.fullscreen:
			self.win.unfullscreen()
			self.fullscreen = False
		else:
			self.win.fullscreen()
			self.fullscreen = True

	def on_expose(self, widget, event=None):
		# Make sure the object is initialized
		if widget.window is None:
			return

		# Widget size
		ww, wh = widget.window.get_size()

		# Manual double buffering (since we use direct drawing instead of
		# calling self.da.queue_draw())
		widget.window.begin_paint_rect(gtk.gdk.Rectangle(0, 0, ww, wh))

		cr = widget.window.cairo_create()
		cr.set_source_rgb(1, 1, 1)

		# Scale
		scale = min(ww/self.pw, wh/self.ph)
		cr.scale(scale, scale)

		cr.rectangle(0, 0, ww, wh)
		cr.fill()
		self.page.render(cr)

		# Blit off-screen buffer to screen
		widget.window.end_paint()

class Presenter:
	def __init__(self, current, next, number, total, event_callback):
		black = gtk.gdk.Color(0, 0, 0)

		self.start_time = 0
		self.number_total = total

		# Window
		win = gtk.Window(gtk.WINDOW_TOPLEVEL)
		win.set_title("pympress presenter")
		win.set_default_size(800, 600)
		#~ win.modify_bg(gtk.STATE_NORMAL, black)
		win.connect("delete-event", gtk.main_quit)

		# Horizontal box
		hbox = gtk.HBox(True)
		win.add(hbox)

		# Aspect frame for current page
		self.frame_current = gtk.AspectFrame(ratio=4./3., obey_child=False)
		#~ self.frame_current.modify_bg(gtk.STATE_NORMAL, black)
		hbox.pack_start(self.frame_current)

		# Drawing area for current page
		self.da_current = gtk.DrawingArea()
		self.da_current.modify_bg(gtk.STATE_NORMAL, black)
		self.da_current.connect("expose-event", self.on_expose)
		self.frame_current.add(self.da_current)

		# Vertical box
		vbox = gtk.VBox(False)
		hbox.pack_start(vbox)

		# Text label
		self.label = gtk.Label()
		self.label.set_justify(gtk.JUSTIFY_CENTER)
		self.label.set_use_markup(True)
		vbox.pack_start(self.label, False, False)

		# Aspect frame for next page
		self.frame_next = gtk.AspectFrame(ratio=4./3., obey_child=False)
		#~ self.frame_next.modify_bg(gtk.STATE_NORMAL, black)
		vbox.pack_start(self.frame_next)

		# Drawing area for next page
		self.da_next = gtk.DrawingArea()
		self.da_next.modify_bg(gtk.STATE_NORMAL, black)
		self.da_next.connect("expose-event", self.on_expose)
		self.frame_next.add(self.da_next)

		# Add events
		win.add_events(gtk.gdk.KEY_PRESS_MASK | gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.SCROLL_MASK)
		win.connect("key-press-event", event_callback)
		win.connect("button-press-event", event_callback)
		win.connect("scroll-event", event_callback)

		# Set page
		self.set_page(current, next, number, False)

		# Setup timer
		gobject.timeout_add(1000, self.update_text)

		win.show_all()

	def on_expose(self, widget, event):
		cr = widget.window.cairo_create()
		cr.set_source_rgb(1, 1, 1)

		# Widget size
		ww, wh = widget.window.get_size()

		# Page-specific stuff (dirty)
		page = self.page_current
		pw, ph = self.pw_cur, self.ph_cur
		if widget == self.da_next:
			page = self.page_next
			pw, ph = self.pw_next, self.ph_next

		# Scale
		scale = min(ww/pw, wh/ph)
		cr.scale(scale, scale)

		cr.rectangle(0, 0, ww, wh)
		cr.fill()

		if page is not None:
			page.render(cr)

	def set_page(self, current, next, number, start = True):
		self.page_current = current
		self.page_next = next
		self.number_current = number

		# Page sizes
		self.pw_cur, self.ph_cur = self.page_current.get_size()

		# Aspect ratios
		pr = self.pw_cur / self.ph_cur
		self.frame_current.set_property("ratio", pr)

		# Same thing for next page if it's set
		if self.page_next is not None:
			self.pw_next, self.ph_next = self.page_next.get_size()
			pr = self.pw_next / self.ph_next
			self.frame_next.set_property("ratio", pr)

		# Start counter if needed
		if start and self.start_time == 0:
			self.start_time = time.time()

		# Update display
		self.update_text()

		self.da_current.queue_draw()
		self.da_next.queue_draw()

	def update_text(self):
		text = "%s\n\n%s\nSlide %d/%d"

		# Current time
		cur_time = time.strftime("%H:%M:%S")

		# Time elapsed since the beginning of the presentation
		delta = time.time() - self.start_time
		if self.start_time == 0:
			delta = 0
		elapsed = "%02d:%02d" % (int(delta/60), int(delta%60))

		text = text % (cur_time, elapsed, self.number_current+1, self.number_total)
		text = "<span font='36'>%s</span>" % text
		self.label.set_markup(text)
		return True

if __name__ == '__main__':
	# PDF file to open
	name = None
	if len(sys.argv) > 1:
		name = os.path.abspath(sys.argv[1])
	else:
		# Use a GTK file dialog to choose file
		dialog = gtk.FileChooserDialog("Open...", None,
		                               gtk.FILE_CHOOSER_ACTION_OPEN,
		                               (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
		                                gtk.STOCK_OPEN, gtk.RESPONSE_OK))
		dialog.set_default_response(gtk.RESPONSE_OK)

		filter = gtk.FileFilter()
		filter.set_name("PDF files")
		filter.add_mime_type("application/pdf")
		filter.add_pattern("*.pdf")
		dialog.add_filter(filter)

		filter = gtk.FileFilter()
		filter.set_name("All files")
		filter.add_pattern("*")
		dialog.add_filter(filter)

		response = dialog.run()
		if response == gtk.RESPONSE_OK:
			name =  dialog.get_filename()
		elif response != gtk.RESPONSE_CANCEL:
			raise ValueError("Invalid response")

		dialog.destroy()

	if name is None:
		# Use a GTK dialog to tell we need a file
		msg="""No file selected!\n\nYou can specify the PDF file to open on the command line if you don't want to use the "Open File" dialog."""
		dialog = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK, message_format=msg)
		dialog.run()
		sys.exit(1)
	else:
		doc = Document("file://" + name)
		doc.run()