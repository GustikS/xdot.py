# Copyright 2008-2015 Jose Fonseca
# Copyright 2008-2015 Jose Fonseca
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import math
import os
import re
import subprocess
import sys
import time
import json

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('PangoCairo', '1.0')


from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk

# See http://www.graphviz.org/pub/scm/graphviz-cairo/plugin/cairo/gvrender_cairo.c

# For pygtk inspiration and guidance see:
# - http://mirageiv.berlios.de/
# - http://comix.sourceforge.net/

from . import actions
from ..dot.lexer import ParseError
from ..dot.parser import XDotParser
from . import animation
from . import actions
from .elements import Graph, Node

import visualization


class DotWidget(Gtk.DrawingArea):
    """GTK widget that draws dot graphs."""

    # TODO GTK3: Second argument has to be of type Gdk.EventButton instead of object.
    __gsignals__ = {
        'clicked': (GObject.SIGNAL_RUN_LAST, None, (str, object)),
        'error': (GObject.SIGNAL_RUN_LAST, None, (str,)),
        'history': (GObject.SIGNAL_RUN_LAST, None, (bool, bool))
    }

    filter = 'dot'

    def __init__(self):
        Gtk.DrawingArea.__init__(self)

        self.graph = Graph()
        self.openfilename = None

        self.set_can_focus(True)

        self.connect("draw", self.on_draw)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.connect("button-press-event", self.on_area_button_press)
        self.connect("button-release-event", self.on_area_button_release)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.POINTER_MOTION_HINT_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.SCROLL_MASK)
        self.connect("motion-notify-event", self.on_area_motion_notify)
        self.connect("scroll-event", self.on_area_scroll_event)
        self.connect("size-allocate", self.on_area_size_allocate)

        self.connect('key-press-event', self.on_key_press_event)
        self.last_mtime = None

        GLib.timeout_add(1000, self.update)

        self.x, self.y = 0.0, 0.0
        self.zoom_ratio = 1.0
        self.zoom_to_fit_on_resize = False
        self.animation = animation.NoAnimation(self)
        self.drag_action = actions.NullAction(self)
        self.presstime = None
        self.highlight = None
        self.highlight_search = False
        self.history_back = []
        self.history_forward = []

        self.textbuffers = []
        self.tags = []

        self.reload_need = False
        self.last_clicked_parameter_node = ""

    def error_dialog(self, message):
        self.emit('error', message)

    def set_filter(self, filter):
        self.filter = filter

    def run_filter(self, dotcode):
        if not self.filter:
            return dotcode
        try:
            p = subprocess.Popen(
                [self.filter, '-Txdot'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                universal_newlines=False
            )
        except OSError as exc:
            error = '%s: %s' % (self.filter, exc.strerror)
            p = subprocess.CalledProcessError(exc.errno, self.filter, exc.strerror)
        else:
            xdotcode, error = p.communicate(dotcode)
            error = error.decode()
        error = error.rstrip()
        if error:
            sys.stderr.write(error + '\n')
        if p.returncode != 0:
            self.error_dialog(error)
            return None
        return xdotcode

    def _set_dotcode(self, dotcode, filename=None, center=True):
        # By default DOT language is UTF-8, but it accepts other encodings
        assert isinstance(dotcode, bytes)
        xdotcode = self.run_filter(dotcode)
        if xdotcode is None:
            return False
        try:
            self.set_xdotcode(xdotcode, center=center)
        except ParseError as ex:
            self.error_dialog(str(ex))
            return False
        else:
            return True

    def set_dotcode(self, dotcode, filename=None, center=True):
        self.openfilename = None
        if self._set_dotcode(dotcode, filename, center=center):
            if filename is None:
                self.last_mtime = None
            else:
                self.last_mtime = os.stat(filename).st_mtime
            self.openfilename = filename
            return True

    def set_xdotcode(self, xdotcode, center=True):
        assert isinstance(xdotcode, bytes)
        parser = XDotParser(xdotcode)
        self.graph = parser.parse()
        self.zoom_image(self.zoom_ratio, center=center)

    def reload(self, add_to_node="", add_existing_node=""):
        if not self.reload_need:
            return
        start_iter = self.textbuffers[0].get_start_iter()
        end_iter = self.textbuffers[0].get_end_iter()
        text = self.textbuffers[0].get_text(start_iter, end_iter, True)
        if add_to_node != "":
            visualization_tool = visualization.VisualizationTool("temp", text, add_to=add_to_node, existing_node=add_existing_node)
            resultDOT, json_text = visualization_tool.visualize_template()
            self.textbuffers[0].set_text(json.dumps(json_text, indent=2))
        else:
            visualization_tool = visualization.VisualizationTool("temp", text)
            resultDOT = visualization_tool.visualize_template()
        self._set_dotcode(resultDOT.encode("utf-8"), "temp.dot")
        self.textbuffers[1].set_text(resultDOT)
        self.zoom_to_fit()
        self.reload_need = False

    def update(self):
        if self.openfilename is not None:
            current_mtime = os.stat(self.openfilename).st_mtime
            if current_mtime != self.last_mtime:
                self.last_mtime = current_mtime
                self.reload()
        return True

    def _draw_graph(self, cr, rect):
        w, h = float(rect.width), float(rect.height)
        cx, cy = 0.5 * w, 0.5 * h
        x, y, ratio = self.x, self.y, self.zoom_ratio
        x0, y0 = x - cx / ratio, y - cy / ratio
        x1, y1 = x0 + w / ratio, y0 + h / ratio
        bounding = (x0, y0, x1, y1)

        cr.translate(cx, cy)
        cr.scale(ratio, ratio)
        cr.translate(-x, -y)
        self.graph.draw(cr, highlight_items=self.highlight, bounding=bounding)

    def on_draw(self, widget, cr):
        rect = self.get_allocation()
        Gtk.render_background(self.get_style_context(), cr, 0, 0,
                              rect.width, rect.height)

        cr.save()
        self._draw_graph(cr, rect)
        cr.restore()

        self.drag_action.draw(cr)

        return False

    def get_current_pos(self):
        return self.x, self.y

    def set_current_pos(self, x, y):
        self.x = x
        self.y = y
        self.queue_draw()

    def set_highlight(self, items, search=False):
        # Enable or disable search highlight
        if search:
            self.highlight_search = items is not None
        # Ignore cursor highlight while searching
        if self.highlight_search and not search:
            return
        if self.highlight != items:
            self.highlight = items
            self.queue_draw()

    def zoom_image(self, zoom_ratio, center=False, pos=None):
        # Constrain zoom ratio to a sane range to prevent numeric instability.
        zoom_ratio = min(zoom_ratio, 1E4)
        zoom_ratio = max(zoom_ratio, 1E-6)

        if center:
            self.x = self.graph.width/2
            self.y = self.graph.height/2
        elif pos is not None:
            rect = self.get_allocation()
            x, y = pos
            x -= 0.5*rect.width
            y -= 0.5*rect.height
            self.x += x / self.zoom_ratio - x / zoom_ratio
            self.y += y / self.zoom_ratio - y / zoom_ratio
        self.zoom_ratio = zoom_ratio
        self.zoom_to_fit_on_resize = False
        self.queue_draw()

    def zoom_to_area(self, x1, y1, x2, y2):
        rect = self.get_allocation()
        width = abs(x1 - x2)
        height = abs(y1 - y2)
        if width == 0 and height == 0:
            self.zoom_ratio *= self.ZOOM_INCREMENT
        else:
            self.zoom_ratio = min(
                float(rect.width)/float(width),
                float(rect.height)/float(height)
            )
        self.zoom_to_fit_on_resize = False
        self.x = (x1 + x2) / 2
        self.y = (y1 + y2) / 2
        self.queue_draw()

    def zoom_to_fit(self):
        rect = self.get_allocation()
        rect.x += self.ZOOM_TO_FIT_MARGIN
        rect.y += self.ZOOM_TO_FIT_MARGIN
        rect.width -= 2 * self.ZOOM_TO_FIT_MARGIN
        rect.height -= 2 * self.ZOOM_TO_FIT_MARGIN
        zoom_ratio = min(
            float(rect.width)/float(self.graph.width),
            float(rect.height)/float(self.graph.height)
        )
        self.zoom_image(zoom_ratio, center=True)
        self.zoom_to_fit_on_resize = True

    ZOOM_INCREMENT = 1.25
    ZOOM_TO_FIT_MARGIN = 12

    def on_zoom_in(self, action):
        self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)

    def on_zoom_out(self, action):
        self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)

    def on_zoom_fit(self, action):
        self.zoom_to_fit()

    def on_zoom_100(self, action):
        self.zoom_image(1.0)

    POS_INCREMENT = 100

    def on_key_press_event(self, widget, event):
        if event.keyval == Gdk.KEY_Left:
            self.x -= self.POS_INCREMENT/self.zoom_ratio
            self.queue_draw()
            return True
        if event.keyval == Gdk.KEY_Right:
            self.x += self.POS_INCREMENT/self.zoom_ratio
            self.queue_draw()
            return True
        if event.keyval == Gdk.KEY_Up:
            self.y -= self.POS_INCREMENT/self.zoom_ratio
            self.queue_draw()
            return True
        if event.keyval == Gdk.KEY_Down:
            self.y += self.POS_INCREMENT/self.zoom_ratio
            self.queue_draw()
            return True
        if event.keyval in (Gdk.KEY_Page_Up,
                            Gdk.KEY_plus,
                            Gdk.KEY_equal,
                            Gdk.KEY_KP_Add):
            self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)
            self.queue_draw()
            return True
        if event.keyval in (Gdk.KEY_Page_Down,
                            Gdk.KEY_minus,
                            Gdk.KEY_KP_Subtract):
            self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)
            self.queue_draw()
            return True
        if event.keyval == Gdk.KEY_Escape:
            self.drag_action.abort()
            self.drag_action = actions.NullAction(self)
            return True
        if event.keyval == Gdk.KEY_r:
            self.reload()
            return True
        if event.keyval == Gdk.KEY_f:
            win = widget.get_toplevel()
            find_toolitem = win.uimanager.get_widget('/ToolBar/Find')
            textentry = find_toolitem.get_children()
            win.set_focus(textentry[0])
            return True
        if event.keyval == Gdk.KEY_q:
            Gtk.main_quit()
            return True
        if event.keyval == Gdk.KEY_p:
            self.on_print()
            return True
        return False

    print_settings = None

    def on_print(self, action=None):
        print_op = Gtk.PrintOperation()

        if self.print_settings is not None:
            print_op.set_print_settings(self.print_settings)

        print_op.connect("begin_print", self.begin_print)
        print_op.connect("draw_page", self.draw_page)

        res = print_op.run(Gtk.PrintOperationAction.PRINT_DIALOG, self.get_toplevel())
        if res == Gtk.PrintOperationResult.APPLY:
            self.print_settings = print_op.get_print_settings()

    def begin_print(self, operation, context):
        operation.set_n_pages(1)
        return True

    def draw_page(self, operation, context, page_nr):
        cr = context.get_cairo_context()
        rect = self.get_allocation()
        self._draw_graph(cr, rect)

    def get_drag_action(self, event):
        state = event.state
        if event.button in (1, 2):  # left or middle button
            modifiers = Gtk.accelerator_get_default_mod_mask()
            if state & modifiers == Gdk.ModifierType.CONTROL_MASK or state & modifiers == Gdk.ModifierType.SHIFT_MASK :
                return actions.ZoomAction
            #elif state & modifiers == Gdk.ModifierType.SHIFT_MASK:
            #    return actions.ZoomAreaAction
            else:
                return actions.PanAction
        return actions.NullAction

    def on_area_button_press(self, area, event):
        self.animation.stop()
        self.drag_action.abort()
        action_type = self.get_drag_action(event)
        self.drag_action = action_type(self)
        self.drag_action.on_button_press(event)
        self.presstime = time.time()
        self.pressx = event.x
        self.pressy = event.y
        return False

    def is_click(self, event, click_fuzz=4, click_timeout=1.0):
        assert event.type == Gdk.EventType.BUTTON_RELEASE
        if self.presstime is None:
            # got a button release without seeing the press?
            return False
        # XXX instead of doing this complicated logic, shouldn't we listen
        # for gtk's clicked event instead?
        deltax = self.pressx - event.x
        deltay = self.pressy - event.y
        return (time.time() < self.presstime + click_timeout and
                math.hypot(deltax, deltay) < click_fuzz)

    def search_and_mark(self, text, i, start):
        end = self.textbuffers[i].get_end_iter()
        match = start.forward_search(text, 0, end)
        if match is not None:
            match_start, match_end = match
            self.textbuffers[i].apply_tag(self.tags[i], match_start, match_end)
            self.search_and_mark(text, i, match_end)
            if i == 0:
                self.textviewJSON.scroll_to_iter(match_start, 0.0, True, 0.5, 0.5)

    def on_click(self, element, event):
        """Override this method in subclass to process
        click events. Note that element can be None
        (click on empty space)."""

        if isinstance(element, Node):
            node_id = element.id.decode("utf8")

            # search and mark node name in textbuffers
            self.search_through_text_buffers_and_mark(node_id)

            # Check if action "add nodes" triggered by mouse and keyboard combinations
            state = event.state
            modifiers = Gtk.accelerator_get_default_mod_mask()
            # CTRL + left click triggers new paramater to a cliked node
            if state & modifiers == Gdk.ModifierType.CONTROL_MASK:
                self.reload_need = True
                self.reload(node_id)
            # SHIFT + left click connect two nodes via parameter
            if state & modifiers == Gdk.ModifierType.SHIFT_MASK:
                if self.last_clicked_parameter_node != "":
                    self.reload_need = True
                    self.reload(node_id, self.last_clicked_parameter_node)
                    self.last_clicked_parameter_node = ""
                else:
                    self.last_clicked_parameter_node = node_id
            else:
                self.last_clicked_parameter_node = ""

        else:
            self.last_clicked_parameter_node = ""

        return True

    def search_through_text_buffers_and_mark(self, node_id):
        i = 0
        for textbuffer in self.textbuffers:
            start = textbuffer.get_start_iter()
            end = textbuffer.get_end_iter()
            textbuffer.remove_all_tags(start, end)
            self.search_and_mark('"object_name": "' + node_id, i, textbuffer.get_start_iter())
            i = i + 1

    def on_area_button_release(self, area, event):
        self.drag_action.on_button_release(event)
        self.drag_action = actions.NullAction(self)
        x, y = int(event.x), int(event.y)
        if self.is_click(event):
            el = self.get_element(x, y)
            if self.on_click(el, event):
                return True

            if event.button == 1:
                self.emit('clicked', url.url, event)
                return True

        if event.button == 1 or event.button == 2:
            return True
        return False

    def on_area_scroll_event(self, area, event):
        if event.direction == Gdk.ScrollDirection.UP:
            self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT,
                            pos=(event.x, event.y))
            return True
        if event.direction == Gdk.ScrollDirection.DOWN:
            self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT,
                            pos=(event.x, event.y))
            return True
        return False

    def on_area_motion_notify(self, area, event):
        self.drag_action.on_motion_notify(event)
        return True

    def on_area_size_allocate(self, area, allocation):
        if self.zoom_to_fit_on_resize:
            self.zoom_to_fit()

    def animate_to(self, x, y):
        del self.history_forward[:]
        self.history_back.append(self.get_current_pos())
        self.history_changed()
        self._animate_to(x, y)

    def _animate_to(self, x, y):
        self.animation = animation.ZoomToAnimation(self, x, y)
        self.animation.start()

    def history_changed(self):
        self.emit(
            'history',
            bool(self.history_back),
            bool(self.history_forward))

    def on_go_back(self, action=None):
        try:
            item = self.history_back.pop()
        except LookupError:
            return
        self.history_forward.append(self.get_current_pos())
        self.history_changed()
        self._animate_to(*item)

    def on_go_forward(self, action=None):
        try:
            item = self.history_forward.pop()
        except LookupError:
            return
        self.history_back.append(self.get_current_pos())
        self.history_changed()
        self._animate_to(*item)

    def window2graph(self, x, y):
        rect = self.get_allocation()
        x -= 0.5*rect.width
        y -= 0.5*rect.height
        x /= self.zoom_ratio
        y /= self.zoom_ratio
        x += self.x
        y += self.y
        return x, y

    def get_element(self, x, y):
        x, y = self.window2graph(x, y)
        return self.graph.get_element(x, y)

    def get_url(self, x, y):
        x, y = self.window2graph(x, y)
        return self.graph.get_url(x, y)

    def get_jump(self, x, y):
        x, y = self.window2graph(x, y)
        return self.graph.get_jump(x, y)


class FindMenuToolAction(Gtk.Action):
    __gtype_name__ = "FindMenuToolAction"

    def do_create_tool_item(self):
        return Gtk.ToolItem()


class DotWindow(Gtk.Window):

    ui = '''
    <ui>
        <toolbar name="ToolBar">
            <toolitem action="Open"/>
            <toolitem action="Reload"/>
            <toolitem action="Save"/>
            <separator expand="true"/>
            <toolitem action="ZoomIn"/>
            <toolitem action="ZoomOut"/>
            <toolitem action="ZoomFit"/>
            <toolitem action="Zoom100"/>
            <separator/>
            <toolitem name="Find" action="Find"/>
        </toolbar>
    </ui>
    '''

    base_title = 'Dot Viewer'

    def __init__(self, widget=None, width=1000, height=500):
        Gtk.Window.__init__(self)

        self.graph = Graph()

        window = self

        window.set_title(self.base_title)
        window.set_default_size(width, height)

        #settings = Gtk.Settings.get_default()
        #settings.set_property("gtk-theme-name", "Arc")
        #settings.set_property("gtk-application-prefer-dark-theme",
        #                      False)  # if you want use dark theme, set second arg to True

        #grid = Gtk.Grid()
        #flowbox = Gtk.FlowBox()
        #flowbox.set_valign(Gtk.Align.START)
        #window.add(flowbox)

        self.box = Gtk.Box(spacing=0)
        window.add(self.box)

        scrolledWindowJSON = Gtk.ScrolledWindow()
        scrolledWindowJSON.set_hexpand(True)
        scrolledWindowJSON.set_vexpand(True)
        self.textviewJSON = Gtk.TextView()
        self.textbufferJSON = self.textviewJSON.get_buffer()
        self.textbufferJSON.set_text("Just some JSON text with Hello and World.\nAs World example.")
        scrolledWindowJSON.add(self.textviewJSON)

        scrolledWindowDOT= Gtk.ScrolledWindow()
        scrolledWindowDOT.set_hexpand(True)
        scrolledWindowDOT.set_vexpand(True)
        self.textviewDOT = Gtk.TextView()
        self.textbufferDOT = self.textviewDOT.get_buffer()
        self.textbufferDOT.set_text("HERE ONLY DOT TEXT \n WHICH CANNOT BE CHANGED")
        scrolledWindowDOT.add(self.textviewDOT)
        self.textviewDOT.set_editable(False)

        self.tag_markedJSON = self.textbufferJSON.create_tag("found", background="gray")
        self.tag_markedDOT = self.textbufferDOT.create_tag("found", background="gray")

        #start = self.textbufferJSON.get_start_iter()
        #end = self.textbufferJSON.get_end_iter()
        #match = start.forward_search("some", 0, end)
        #self.textbufferJSON.apply_tag(self.tag_markedJSON, match[0], match[1])

        scrolledWindowJSON.set_min_content_width(350)
        scrolledWindowDOT.set_min_content_width(350)

        notebook = Gtk.Notebook()
        notebook.append_page(scrolledWindowJSON, Gtk.Label("JSON text"))
        notebook.append_page(scrolledWindowDOT, Gtk.Label("DOT graph"))

        vbox = Gtk.VBox()
        self.box.pack_start(notebook, True, True, 0)
        self.box.pack_start(vbox, True, True, 0)


        self.dotwidget = widget or DotWidget()
        self.dotwidget.connect("error", lambda e, m: self.error_dialog(m))
        self.dotwidget.connect("history", self.on_history)

        self.dotwidget.textbuffers.extend([self.textbufferJSON, self.textbufferDOT])
        self.dotwidget.textviewJSON = self.textviewJSON
        self.dotwidget.tags.extend([self.tag_markedJSON, self.tag_markedDOT])

        # Create a UIManager instance
        uimanager = self.uimanager = Gtk.UIManager()

        # Add the accelerator group to the toplevel window
        accelgroup = uimanager.get_accel_group()
        window.add_accel_group(accelgroup)

        # Create an ActionGroup
        actiongroup = Gtk.ActionGroup('Actions')
        self.actiongroup = actiongroup

        # Create actions
        actiongroup.add_actions((
            ('Open', Gtk.STOCK_OPEN, None, None, None, self.on_open),
            ('Reload', Gtk.STOCK_REFRESH, None, None, None, self.on_reload),
            ('Save', Gtk.STOCK_PRINT, None, None, None, self.on_save),
            #('Print', Gtk.STOCK_PRINT, None, None,
            # "Prints the currently visible part of the graph", self.dotwidget.on_print),
            ('ZoomIn', Gtk.STOCK_ZOOM_IN, None, None, None, self.dotwidget.on_zoom_in),
            ('ZoomOut', Gtk.STOCK_ZOOM_OUT, None, None, None, self.dotwidget.on_zoom_out),
            ('ZoomFit', Gtk.STOCK_ZOOM_FIT, None, None, None, self.dotwidget.on_zoom_fit),
            ('Zoom100', Gtk.STOCK_ZOOM_100, None, None, None, self.dotwidget.on_zoom_100),
        ))

        #self.back_action = Gtk.Action('Back', None, None, Gtk.STOCK_GO_BACK)
        #self.back_action.set_sensitive(False)
        #self.back_action.connect("activate", self.dotwidget.on_go_back)
        #actiongroup.add_action(self.back_action)

        #self.forward_action = Gtk.Action('Forward', None, None, Gtk.STOCK_GO_FORWARD)
        #self.forward_action.set_sensitive(False)
        #self.forward_action.connect("activate", self.dotwidget.on_go_forward)
        #actiongroup.add_action(self.forward_action)

        find_action = FindMenuToolAction("Find", None,
                                         "Find a node by name", None)
        actiongroup.add_action(find_action)

        # Add the actiongroup to the uimanager
        uimanager.insert_action_group(actiongroup, 0)

        # Add a UI descrption
        uimanager.add_ui_from_string(self.ui)

        # Create a Toolbar
        toolbar = uimanager.get_widget('/ToolBar')
        vbox.pack_start(toolbar, False, False, 0)

        vbox.pack_start(self.dotwidget, True, True, 0)

        self.last_open_dir = "."

        self.set_focus(self.dotwidget)

        # Add Find text search
        find_toolitem = uimanager.get_widget('/ToolBar/Find')
        self.textentry = Gtk.Entry(max_length=20)
        self.textentry.set_icon_from_stock(0, Gtk.STOCK_FIND)
        find_toolitem.add(self.textentry)

        self.textentry.set_activates_default(True)
        self.textentry.connect("activate", self.textentry_activate, self.textentry);
        self.textentry.connect("changed", self.textentry_changed, self.textentry);

        self.show_all()

    def find_text(self, entry_text):
        found_items = []
        dot_widget = self.dotwidget
        regexp = re.compile(entry_text)
        for element in dot_widget.graph.nodes + dot_widget.graph.edges:
            if element.search_text(regexp):
                found_items.append(element)
        return found_items

    def textentry_changed(self, widget, entry):
        entry_text = entry.get_text()
        dot_widget = self.dotwidget
        if not entry_text:
            dot_widget.set_highlight(None, search=True)
            return

        found_items = self.find_text(entry_text)
        dot_widget.set_highlight(found_items, search=True)

    def textentry_activate(self, widget, entry):
        entry_text = entry.get_text()
        dot_widget = self.dotwidget
        if not entry_text:
            dot_widget.set_highlight(None, search=True)
            return

        found_items = self.find_text(entry_text)
        dot_widget.set_highlight(found_items, search=True)
        #if(len(found_items) == 1):
        #    dot_widget.animate_to(found_items[0].x, found_items[0].y)

    def set_filter(self, filter):
        self.dotwidget.set_filter(filter)

    def set_dotcode(self, dotcode, filename=None):
        if self.dotwidget.set_dotcode(dotcode, filename):
            self.update_title(filename)
            self.dotwidget.zoom_to_fit()

    def set_xdotcode(self, xdotcode, filename=None):
        if self.dotwidget.set_xdotcode(xdotcode):
            self.update_title(filename)
            self.dotwidget.zoom_to_fit()

    def update_title(self, filename=None):
        if filename is None:
            self.set_title(self.base_title)
        else:
            self.set_title(os.path.basename(filename) + ' - ' + self.base_title)

    def open_file(self, filename):
        try:
            fp = open(filename, 'rb')
            self.set_dotcode(fp.read(), filename)
            fp.close()
        except IOError as ex:
            self.error_dialog(str(ex))

    def on_open(self, action):
        self.dotwidget.reload_need = True
        chooser = Gtk.FileChooserDialog(parent=self,
                                        title="Open dot File",
                                        action=Gtk.FileChooserAction.OPEN,
                                        buttons=(Gtk.STOCK_CANCEL,
                                                 Gtk.ResponseType.CANCEL,
                                                 Gtk.STOCK_OPEN,
                                                 Gtk.ResponseType.OK))
        chooser.set_default_response(Gtk.ResponseType.OK)
        chooser.set_current_folder(self.last_open_dir)
        filter = Gtk.FileFilter()
        filter.set_name("JSON files")
        filter.add_pattern("*.json")
        chooser.add_filter(filter)
        filter = Gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        chooser.add_filter(filter)
        if chooser.run() == Gtk.ResponseType.OK:
            filename = chooser.get_filename()
            self.last_open_dir = chooser.get_current_folder()
            chooser.destroy()
            json_src = ""
            with open(filename, 'r') as content_file:
                json_src = content_file.read()
            visualization_tool = visualization.VisualizationTool("temp", json_src)
            resultDOT = visualization_tool.visualize_template()
            self.textbufferJSON.set_text(json_src)
            self.textbufferDOT.set_text(resultDOT)
            self.set_dotcode(resultDOT.encode("utf-8"), "temp.dot")
            self.last_filename = filename
        else:
            chooser.destroy()

    def on_save(self, action):
        start_iter = self.textbufferJSON.get_start_iter()
        end_iter = self.textbufferJSON.get_end_iter()
        text = self.textbufferJSON.get_text(start_iter, end_iter, True)
        with open(self.last_filename, 'w') as content_file:
            content_file.write(text)

    def on_reload(self, action):
        self.dotwidget.reload_need = True
        self.dotwidget.reload()

    def error_dialog(self, message):
        dlg = Gtk.MessageDialog(parent=self,
                                type=Gtk.MessageType.ERROR,
                                message_format=message,
                                buttons=Gtk.ButtonsType.OK)
        dlg.set_title(self.base_title)
        dlg.run()
        dlg.destroy()

    def on_history(self, action, has_back, has_forward):
        self.back_action.set_sensitive(has_back)
        self.forward_action.set_sensitive(has_forward)
