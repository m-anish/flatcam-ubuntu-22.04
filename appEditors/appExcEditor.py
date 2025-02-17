# ##########################################################
# FlatCAM: 2D Post-processing for Manufacturing            #
# File Author: Marius Adrian Stanciu (c)                   #
# Date: 8/17/2019                                          #
# MIT Licence                                              #
# ##########################################################

from camlib import distance, arc, AppRTreeStorage

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtCore import Qt
from appEditors.exc_plugins.ExcDrillPlugin import ExcDrillEditorTool
from appEditors.exc_plugins.ExcSlotPlugin import ExcSlotEditorTool
from appEditors.exc_plugins.ExcDrillArrayPlugin import ExcDrillArrayEditorTool
from appEditors.exc_plugins.ExcSlotArrayPlugin import ExcSlotArrayEditorTool
from appEditors.exc_plugins.ExcResizePlugin import ExcResizeEditorTool
from appEditors.exc_plugins.ExcCopyPlugin import ExcCopyEditorTool

from appGUI.GUIElements import FCEntry, FCTable, FCDoubleSpinner, FCButton, FCLabel, GLay
from appEditors.appGeoEditor import FCShapeTool, DrawTool, DrawToolShape, DrawToolUtilityShape, AppGeoEditor

from shapely import LineString, LinearRing, MultiLineString, Polygon, MultiPolygon, Point
from shapely.geometry.base import BaseGeometry
from shapely.affinity import scale, rotate, translate
# from appCommon.Common import LoudDict

import numpy as np

from rtree import index as rtindex

import traceback
import math
import logging
from copy import deepcopy

import gettext
import appTranslation as fcTranslate
import builtins

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext

log = logging.getLogger('base')


class SelectEditorExc(FCShapeTool):
    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'drill_select'

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        self.draw_app = draw_app
        self.storage = self.draw_app.storage_dict
        # self.selected = self.draw_app.selected

        # here we store the selected tools
        self.sel_tools = set()

        # here we store all shapes that were selected so we can search for the nearest to our click location
        self.sel_storage = AppExcEditor.make_storage()

        # make sure that the cursor text from the DrillAdd is deleted
        if self.draw_app.app.use_3d_engine and self.draw_app.app.plotcanvas.text_cursor.parent:
            self.draw_app.app.plotcanvas.text_cursor.parent = None
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None

        # make sure that the Tools tab is removed
        try:
            self.draw_app.app.ui.notebook.removeTab(2)
        except Exception:
            pass

    def click(self, point):
        key_modifier = QtWidgets.QApplication.keyboardModifiers()

        if key_modifier == QtCore.Qt.KeyboardModifier.ShiftModifier:
            mod_key = 'Shift'
        elif key_modifier == QtCore.Qt.KeyboardModifier.ControlModifier:
            mod_key = 'Control'
        else:
            mod_key = None

        if mod_key == self.draw_app.app.options["global_mselect_key"]:
            pass
        else:
            self.draw_app.selected = []

    def click_release(self, pos):
        self.draw_app.ui.tools_table_exc.clearSelection()
        xmin, ymin, xmax, ymax = 0, 0, 0, 0

        try:
            for storage in self.draw_app.storage_dict:
                # for sh in self.draw_app.storage_dict[storage].get_objects():
                #     self.sel_storage.insert(sh)
                _, st_closest_shape = self.draw_app.storage_dict[storage].nearest(pos)
                self.sel_storage.insert(st_closest_shape)

            _, closest_shape = self.sel_storage.nearest(pos)

            # constrain selection to happen only within a certain bounding box; it works only for MultiLineStrings
            if isinstance(closest_shape.geo, MultiLineString):
                x_coord, y_coord = closest_shape.geo.geoms[0].xy
                delta = (x_coord[1] - x_coord[0])
                # closest_shape_coords = (((x_coord[0] + delta / 2)), y_coord[0])
                xmin = x_coord[0] - (0.7 * delta)
                xmax = x_coord[0] + (1.7 * delta)
                ymin = y_coord[0] - (0.7 * delta)
                ymax = y_coord[0] + (1.7 * delta)
            elif isinstance(closest_shape.geo, Polygon):
                xmin, ymin, xmax, ymax = closest_shape.geo.bounds
                dx = xmax - xmin
                dy = ymax - ymin
                delta = dx if dx > dy else dy
                xmin -= 0.7 * delta
                xmax += 0.7 * delta
                ymin -= 0.7 * delta
                ymax += 0.7 * delta
        except StopIteration:
            return ""

        if pos[0] < xmin or pos[0] > xmax or pos[1] < ymin or pos[1] > ymax:
            self.draw_app.selected.clear()
        else:
            modifiers = QtWidgets.QApplication.keyboardModifiers()

            if modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier:
                mod_key = 'Shift'
            elif modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
                mod_key = 'Control'
            else:
                mod_key = None

            if mod_key == self.draw_app.app.options["global_mselect_key"]:
                if closest_shape in self.draw_app.selected:
                    self.draw_app.selected.remove(closest_shape)
                else:
                    self.draw_app.selected.append(closest_shape)
            else:
                self.draw_app.selected.clear()
                self.draw_app.selected.append(closest_shape)

            # select the diameter of the selected shape in the tool table
            try:
                self.draw_app.ui.tools_table_exc.cellPressed.disconnect()
            except (TypeError, AttributeError):
                pass

            # if mod_key == self.draw_app.app.options["global_mselect_key"]:
            #     self.draw_app.ui.tools_table_exc.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
            self.sel_tools.clear()

            for shape_s in self.draw_app.selected:
                for storage in self.draw_app.storage_dict:
                    if shape_s in self.draw_app.storage_dict[storage].get_objects():
                        self.sel_tools.add(storage)

            self.draw_app.ui.tools_table_exc.clearSelection()
            for storage in self.sel_tools:
                for k, v in self.draw_app.tool2tooldia.items():
                    if v == storage:
                        self.draw_app.ui.tools_table_exc.selectRow(int(k) - 1)
                        self.draw_app.last_tool_selected = int(k)
                        break

            # self.draw_app.ui.tools_table_exc.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

            self.draw_app.ui.tools_table_exc.cellPressed.connect(self.draw_app.on_row_selected)

        # delete whatever is in selection storage, there is no longer need for those shapes
        self.sel_storage = AppExcEditor.make_storage()

        return ""

        # clicked_pos[0] and clicked_pos[1] are the mouse click coordinates (x, y)
        # for storage in self.draw_app.storage_dict:
        #     for obj_shape in self.draw_app.storage_dict[storage].get_objects():
        #         minx, miny, maxx, maxy = obj_shape.geo.bounds
        #         if (minx <= clicked_pos[0] <= maxx) and (miny <= clicked_pos[1] <= maxy):
        #             over_shape_list.append(obj_shape)
        #
        # try:
        #     # if there is no shape under our click then deselect all shapes
        #     if not over_shape_list:
        #         self.draw_app.selected = []
        #         AppExcEditor.draw_shape_idx = -1
        #         self.draw_app.ui.tools_table_exc.clearSelection()
        #     else:
        #         # if there are shapes under our click then advance through the list of them, one at the time in a
        #         # circular way
        #         AppExcEditor.draw_shape_idx = (AppExcEditor.draw_shape_idx + 1) % len(over_shape_list)
        #         obj_to_add = over_shape_list[int(AppExcEditor.draw_shape_idx)]
        #
        #         if self.draw_app.app.options["global_mselect_key"] == 'Shift':
        #             if self.draw_app.modifiers == Qt.KeyboardModifier.ShiftModifier:
        #                 if obj_to_add in self.draw_app.selected:
        #                     self.draw_app.selected.remove(obj_to_add)
        #                 else:
        #                     self.draw_app.selected.append(obj_to_add)
        #             else:
        #                 self.draw_app.selected = []
        #                 self.draw_app.selected.append(obj_to_add)
        #         else:
        #             # if CONTROL key is pressed then we add to the selected list the current shape but if it's already
        #             # in the selected list, we removed it. Therefore first click selects, second deselects.
        #             if self.draw_app.modifiers == Qt.KeyboardModifier.ControlModifier:
        #                 if obj_to_add in self.draw_app.selected:
        #                     self.draw_app.selected.remove(obj_to_add)
        #                 else:
        #                     self.draw_app.selected.append(obj_to_add)
        #             else:
        #                 self.draw_app.selected = []
        #                 self.draw_app.selected.append(obj_to_add)
        #
        #     for storage in self.draw_app.storage_dict:
        #         for shape in self.draw_app.selected:
        #             if shape in self.draw_app.storage_dict[storage].get_objects():
        #                 for key in self.draw_app.tool2tooldia:
        #                     if self.draw_app.tool2tooldia[key] == storage:
        #                         item = self.draw_app.ui.tools_table_exc.item((key - 1), 1)
        #                         item.setSelected(True)
        #                         # self.draw_app.ui.tools_table_exc.selectItem(key - 1)
        #
        # except Exception as e:
        #     log.error("[ERROR] Something went bad. %s" % str(e))
        #     raise

    def clean_up(self):
        pass


class DrillAdd(FCShapeTool):
    """
    Resulting type: MultiLineString
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'drill_add'
        self.draw_app = draw_app
        self.app = self.draw_app.app

        self.cursor_data_control = True

        self.selected_dia = None
        try:
            self.draw_app.app.inform.emit(_("Click to place ..."))
            self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]

            # as a visual marker, select again in tooltable the actual tool that we are using
            # remember that it was deselected when clicking on canvas
            item = self.draw_app.ui.tools_table_exc.item((self.draw_app.last_tool_selected - 1), 1)
            self.draw_app.ui.tools_table_exc.setCurrentItem(item)
        except KeyError:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' % _("To add a drill first select a tool"))
            self.draw_app.select_tool("drill_select")
            return

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass
        self.cursor = QtGui.QCursor(QtGui.QPixmap(self.draw_app.app.resource_location + '/aero_drill.png'))
        QtGui.QGuiApplication.setOverrideCursor(self.cursor)

        # #############################################################################################################
        # Plugin UI
        # #############################################################################################################
        self.drill_tool = ExcDrillEditorTool(self.app, self.draw_app, plugin_name=_("Drill"))
        self.ui = self.drill_tool.ui
        self.drill_tool.run()

        geo = self.utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y))

        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            self.draw_app.draw_utility_geometry(geo=geo)

        if self.app.use_3d_engine:
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = self.draw_cursor_data
        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        self.drill_tool.length = self.draw_app.last_length
        if not self.draw_app.snap_x:
            self.draw_app.snap_x = 0.0
        if not self.draw_app.snap_y:
            self.draw_app.snap_y = 0.0

        self.app.ui.notebook.setTabText(2, _("Drill"))
        if self.app.ui.splitter.sizes()[0] == 0:
            self.app.ui.splitter.setSizes([1, 1])

        self.points = deepcopy(self.draw_app.clicked_pos) if \
            self.draw_app.clicked_pos and self.draw_app.clicked_pos[0] and self.draw_app.clicked_pos[1] else (0.0, 0.0)
        self.drill_point = None

        self.set_plugin_ui()

        # Signals
        try:
            self.ui.add_btn.clicked.disconnect()
        except (AttributeError, TypeError):
            pass
        self.ui.add_btn.clicked.connect(self.on_add_drill)

        self.draw_app.app.inform.emit(_("Click to place ..."))

    def set_plugin_ui(self):
        curr_row = self.draw_app.ui.tools_table_exc.currentRow()
        tool_dia = float(self.draw_app.ui.tools_table_exc.item(curr_row, 1).text())
        self.ui.dia_entry.set_value(tool_dia)
        self.ui.x_entry.set_value(float(self.draw_app.snap_x))
        self.ui.y_entry.set_value(float(self.draw_app.snap_y))

    def click(self, point):
        self.drill_point = point
        self.draw_app.last_length = self.drill_tool.length
        self.ui.x_entry.set_value(float(self.draw_app.snap_x))
        self.ui.y_entry.set_value(float(self.draw_app.snap_y))
        self.make()
        return "Done."

    def utility_geometry(self, data=None):
        return DrawToolUtilityShape(self.util_shape(data))

    def util_shape(self, point):
        self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]

        if point[0] is None and point[1] is None:
            point_x = self.draw_app.x
            point_y = self.draw_app.y
        else:
            point_x = point[0]
            point_y = point[1]

        start_hor_line = ((point_x - (self.selected_dia / 2)), point_y)
        stop_hor_line = ((point_x + (self.selected_dia / 2)), point_y)
        start_vert_line = (point_x, (point_y - (self.selected_dia / 2)))
        stop_vert_line = (point_x, (point_y + (self.selected_dia / 2)))

        return MultiLineString([(start_hor_line, stop_hor_line), (start_vert_line, stop_vert_line)])

    def make(self):
        if self.drill_point is None:
            self.drill_point = (self.draw_app.snap_x, self.draw_app.snap_y)
        self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        # add the point to drills if the diameter is a key in the dict, if not, create it and add the drill location
        # to the value, as a list of itself
        if self.selected_dia in self.draw_app.points_edit:
            self.draw_app.points_edit[self.selected_dia].append(self.drill_point)
        else:
            self.draw_app.points_edit[self.selected_dia] = [self.drill_point]

        self.draw_app.current_storage = self.draw_app.storage_dict[self.selected_dia]
        self.geometry = DrawToolShape(self.util_shape(self.drill_point))
        self.draw_app.in_action = False
        self.complete = True

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass

        self.draw_app.app.inform.emit('[success] %s' % _("Done."))

    def draw_cursor_data(self, pos=None, delete=False):
        if self.cursor_data_control is False:
            self.draw_app.app.plotcanvas.text_cursor.text = ""
            return

        if pos is None:
            pos = self.draw_app.snap_x, self.draw_app.snap_y

        if delete:
            if self.draw_app.app.use_3d_engine:
                self.draw_app.app.plotcanvas.text_cursor.parent = None
                self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None
            return

        if not self.points:
            self.points = self.draw_app.snap_x, self.draw_app.snap_y

        # font size
        qsettings = QtCore.QSettings("Open Source", "FlatCAM_EVO")
        if qsettings.contains("hud_font_size"):
            fsize = qsettings.value('hud_font_size', type=int)
        else:
            fsize = 8

        x = pos[0]
        y = pos[1]
        try:
            length = abs(np.sqrt((x - self.points[0]) ** 2 + (y - self.points[1]) ** 2))
        except IndexError:
            length = self.draw_app.app.dec_format(0.0, self.draw_app.app.decimals)

        x_dec = str(self.draw_app.app.dec_format(x, self.draw_app.app.decimals)) if x else '0.0'
        y_dec = str(self.draw_app.app.dec_format(y, self.draw_app.app.decimals)) if y else '0.0'
        length_dec = str(self.draw_app.app.dec_format(length, self.draw_app.app.decimals)) if length else '0.0'

        units = self.draw_app.app.app_units.lower()
        l1_txt = 'X:   %s [%s]' % (x_dec, units)
        l2_txt = 'Y:   %s [%s]' % (y_dec, units)
        l3_txt = 'L:   %s [%s]' % (length_dec, units)
        cursor_text = '%s\n%s\n\n%s' % (l1_txt, l2_txt, l3_txt)

        if self.draw_app.app.use_3d_engine:
            new_pos = self.draw_app.app.plotcanvas.translate_coords_2((x, y))
            x, y, __, ___ = self.draw_app.app.plotcanvas.translate_coords((new_pos[0]+30, new_pos[1]))

            # text
            self.draw_app.app.plotcanvas.text_cursor.font_size = fsize
            self.draw_app.app.plotcanvas.text_cursor.text = cursor_text
            self.draw_app.app.plotcanvas.text_cursor.pos = x, y
            self.draw_app.app.plotcanvas.text_cursor.anchors = 'left', 'top'

            if self.draw_app.app.plotcanvas.text_cursor.parent is None:
                self.draw_app.app.plotcanvas.text_cursor.parent = self.draw_app.app.plotcanvas.view.scene

    def on_key(self, key):
        # Jump to coords
        if key == QtCore.Qt.Key.Key_J or key == 'J':
            self.draw_app.app.on_jump_to()

        if key in [str(i) for i in range(10)] + ['.', ',', '+', '-', '/', '*'] or \
                key in [QtCore.Qt.Key.Key_0, QtCore.Qt.Key.Key_1, QtCore.Qt.Key.Key_2,
                        QtCore.Qt.Key.Key_3, QtCore.Qt.Key.Key_4, QtCore.Qt.Key.Key_5, QtCore.Qt.Key.Key_6,
                        QtCore.Qt.Key.Key_7, QtCore.Qt.Key.Key_8, QtCore.Qt.Key.Key_9, QtCore.Qt.Key.Key_Minus,
                        QtCore.Qt.Key.Key_Plus, QtCore.Qt.Key.Key_Comma, QtCore.Qt.Key.Key_Period,
                        QtCore.Qt.Key.Key_Slash, QtCore.Qt.Key.Key_Asterisk]:
            try:
                # VisPy keys
                if self.drill_tool.length == self.draw_app.last_length:
                    self.drill_tool.length = str(key.name)
                else:
                    self.drill_tool.length = str(self.drill_tool.length) + str(key.name)
            except AttributeError:
                # Qt keys
                if self.drill_tool.length == self.draw_app.last_length:
                    self.drill_tool.length = chr(key)
                else:
                    self.drill_tool.length = str(self.drill_tool.length) + chr(key)

        if key == 'Enter' or key == QtCore.Qt.Key.Key_Return or key == QtCore.Qt.Key.Key_Enter:
            if self.drill_tool.length != 0:
                target_length = self.drill_tool.length
                if target_length is None:
                    self.drill_tool.length = 0.0
                    return _("Failed.")

                first_pt = self.ui.x_entry.get_value(), self.ui.y_entry.get_value()
                last_pt = self.draw_app.snap_x, self.draw_app.snap_y

                seg_length = math.sqrt((last_pt[0] - first_pt[0])**2 + (last_pt[1] - first_pt[1])**2)
                if seg_length == 0.0:
                    return
                try:
                    new_x = first_pt[0] + (last_pt[0] - first_pt[0]) / seg_length * target_length
                    new_y = first_pt[1] + (last_pt[1] - first_pt[1]) / seg_length * target_length
                except ZeroDivisionError as err:
                    self.clean_up()
                    return '[ERROR_NOTCL] %s %s' % (_("Failed."), str(err).capitalize())

                if first_pt != (new_x, new_y):
                    self.draw_app.app.on_jump_to(custom_location=(new_x, new_y), fit_center=False)
                    self.add_drill(drill_pos=(new_x, new_y))

        if key == 'C' or key == QtCore.Qt.Key.Key_C:
            self.cursor_data_control = not self.cursor_data_control

    def add_drill(self, drill_pos):
        curr_pos = self.draw_app.app.geo_editor.snap(drill_pos[0], drill_pos[1])
        self.draw_app.snap_x = curr_pos[0]
        self.draw_app.snap_y = curr_pos[1]

        self.draw_app.on_canvas_click_left_handler(curr_pos)
        if self.draw_app.active_tool.complete:
            self.draw_app.on_shape_complete()

        self.drill_point = curr_pos
        self.draw_app.clicked_pos = curr_pos

    def on_add_drill(self):
        x = self.ui.x_entry.get_value()
        y = self.ui.y_entry.get_value()
        self.add_drill(drill_pos=(x, y))

    def clean_up(self):
        self.draw_app.selected.clear()
        self.draw_app.ui.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        if self.draw_app.app.use_3d_engine:
            self.draw_app.app.plotcanvas.text_cursor.parent = None
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class DrillArray(FCShapeTool):
    """
    Resulting type: MultiLineString
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'drill_array'
        self.draw_app = draw_app
        self.app = self.draw_app.app

        self.selected_dia = None

        self.drill_axis = 'X'
        self.drill_array = 'linear'    # 'linear'
        self.drill_array_size = None
        self.drill_pitch = None
        self.drill_linear_angle = None

        self.drill_angle = None
        self.drill_direction = None
        self.drill_radius = None

        self.origin = None
        self.destination = None
        self.flag_for_circ_array = None

        self.last_dx = 0
        self.last_dy = 0

        self.pt = []

        self.cursor_data_control = True

        try:
            self.draw_app.app.inform.emit(_("Click to place ..."))
            self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]
            # as a visual marker, select again in tooltable the actual tool that we are using
            # remember that it was deselected when clicking on canvas
            item = self.draw_app.ui.tools_table_exc.item((self.draw_app.last_tool_selected - 1), 1)
            self.draw_app.ui.tools_table_exc.setCurrentItem(item)
        except KeyError:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                          _("To add an Drill Array first select a tool in Tool Table"))
            return

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass
        self.cursor = QtGui.QCursor(QtGui.QPixmap(self.draw_app.app.resource_location + '/aero_drill_array.png'))
        QtGui.QGuiApplication.setOverrideCursor(self.cursor)

        # #############################################################################################################
        # Plugin UI
        # #############################################################################################################
        self.darray_tool = ExcDrillArrayEditorTool(self.app, self.draw_app, plugin_name=_("Drill Array"))
        self.ui = self.darray_tool.ui
        self.darray_tool.run()

        geo = self.utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y), static=True)

        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            self.draw_app.draw_utility_geometry(geo=geo)

        if self.app.use_3d_engine:
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = self.draw_cursor_data
        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        if not self.draw_app.snap_x:
            self.draw_app.snap_x = 0.0
        if not self.draw_app.snap_y:
            self.draw_app.snap_y = 0.0

        self.app.ui.notebook.setTabText(2, _("Drill Array"))
        if self.app.ui.splitter.sizes()[0] == 0:
            self.app.ui.splitter.setSizes([1, 1])

        self.set_plugin_ui()

        # Signals
        try:
            self.ui.add_btn.clicked.disconnect()
        except (AttributeError, TypeError):
            pass
        self.ui.add_btn.clicked.connect(self.on_add_drill_array)

        if self.ui.array_type_radio.get_value() == 'linear':
            self.draw_app.app.inform.emit(_("Click on target location ..."))
        else:
            self.draw_app.app.inform.emit(_("Click on the circular array Center position"))
        # self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

    def set_plugin_ui(self):
        curr_row = self.draw_app.ui.tools_table_exc.currentRow()
        tool_dia = float(self.draw_app.ui.tools_table_exc.item(curr_row, 1).text())
        self.ui.dia_entry.set_value(tool_dia)
        self.ui.x_entry.set_value(float(self.draw_app.snap_x))
        self.ui.y_entry.set_value(float(self.draw_app.snap_y))

        self.ui.array_type_radio.set_value(self.draw_app.last_darray_type)
        self.ui.on_array_type_radio(val=self.ui.array_type_radio.get_value())

        self.ui.array_size_entry.set_value(self.draw_app.last_darray_size)
        self.ui.axis_radio.set_value(self.draw_app.last_darray_lin_dir)
        self.ui.pitch_entry.set_value(self.draw_app.last_darray_pitch)
        self.ui.linear_angle_entry.set_value(self.draw_app.last_darray_lin_angle)
        self.ui.array_dir_radio.set_value(self.draw_app.last_darray_circ_dir)
        self.ui.circular_angle_entry.set_value(self.draw_app.last_darray_circ_angle)
        self.ui.radius_entry.set_value(self.draw_app.last_darray_radius)

    def click(self, point):
        self.ui.x_entry.set_value(float(self.draw_app.snap_x))
        self.ui.y_entry.set_value(float(self.draw_app.snap_y))

        if self.drill_array == 'linear':   # 'Linear'
            self.make()
            return

        if self.flag_for_circ_array is None:
            self.draw_app.in_action = True
            self.pt.append(point)

            self.flag_for_circ_array = True
            self.set_origin(point)
            self.draw_app.app.inform.emit(_("Click on the Circular Array Start position"))
        else:
            self.destination = point
            self.make()
            self.flag_for_circ_array = None

    def set_origin(self, origin):
        self.origin = origin

    def utility_geometry(self, data=None, static=None):
        self.drill_axis = self.ui.axis_radio.get_value()
        self.drill_direction = self.ui.array_dir_radio.get_value()
        self.drill_array = self.ui.array_type_radio.get_value()

        self.drill_array_size = int(self.ui.array_size_entry.get_value())
        self.drill_pitch = float(self.ui.pitch_entry.get_value())
        self.drill_linear_angle = float(self.ui.linear_angle_entry.get_value())
        self.drill_angle = float(self.ui.circular_angle_entry.get_value())

        if self.drill_array == 'linear':   # 'Linear'
            if data[0] is None and data[1] is None:
                dx = self.draw_app.snap_x
                dy = self.draw_app.snap_y
            else:
                dx = data[0]
                dy = data[1]

            geo_list = []
            geo = None
            self.points = [dx, dy]

            for item in range(self.drill_array_size):
                if self.drill_axis == 'X':
                    geo = self.util_shape(((dx + (self.drill_pitch * item)), dy))
                if self.drill_axis == 'Y':
                    geo = self.util_shape((dx, (dy + (self.drill_pitch * item))))
                if self.drill_axis == 'A':
                    x_adj = self.drill_pitch * math.cos(math.radians(self.drill_linear_angle))
                    y_adj = self.drill_pitch * math.sin(math.radians(self.drill_linear_angle))
                    geo = self.util_shape(
                        ((dx + (x_adj * item)), (dy + (y_adj * item)))
                    )

                if static is None or static is False:
                    geo_list.append(translate(geo, xoff=(dx - self.last_dx), yoff=(dy - self.last_dy)))
                else:
                    geo_list.append(geo)
            # self.origin = data

            self.last_dx = dx
            self.last_dy = dy
            return DrawToolUtilityShape(geo_list)
        elif self.drill_array == 'circular':  # 'Circular'
            if data[0] is None and data[1] is None:
                cdx = self.draw_app.snap_x
                cdy = self.draw_app.snap_y
            else:
                cdx = data[0]
                cdy = data[1]

            utility_list = []
            self.points = [cdx, cdy]

            try:
                radius = distance((cdx, cdy), self.origin)
            except Exception:
                radius = 0
            if radius == 0:
                self.draw_app.delete_utility_geometry()
            self.ui.radius_entry.set_value(radius)

            if len(self.pt) >= 1 and radius > 0:
                try:
                    if cdx < self.origin[0]:
                        radius = -radius

                    # draw the temp geometry
                    initial_angle = math.asin((cdy - self.origin[1]) / radius)

                    temp_circular_geo = self.circular_util_shape(radius, initial_angle)

                    # draw the line
                    temp_points = [x for x in self.pt]
                    temp_points.append([cdx, cdy])
                    temp_line = LineString(temp_points)

                    for geo_shape in temp_circular_geo:
                        utility_list.append(geo_shape.geo)
                    utility_list.append(temp_line)

                    return DrawToolUtilityShape(utility_list)
                except Exception as e:
                    log.error("DrillArray.utility_geometry -- circular -> %s" % str(e))

    def circular_util_shape(self, radius, angle):
        self.drill_direction = self.ui.array_dir_radio.get_value()
        self.drill_angle = self.ui.circular_angle_entry.get_value()

        circular_geo = []
        if self.drill_direction == 'CW':
            for i in range(self.drill_array_size):
                angle_radians = math.radians(self.drill_angle * i)
                x = self.origin[0] + radius * math.cos(-angle_radians + angle)
                y = self.origin[1] + radius * math.sin(-angle_radians + angle)

                geo_sol = self.util_shape((x, y))
                # geo_sol = affinity.rotate(geo_sol, angle=(math.pi - angle_radians), use_radians=True)

                circular_geo.append(DrawToolShape(geo_sol))
        else:
            for i in range(self.drill_array_size):
                angle_radians = math.radians(self.drill_angle * i)
                x = self.origin[0] + radius * math.cos(angle_radians + angle)
                y = self.origin[1] + radius * math.sin(angle_radians + angle)

                geo_sol = self.util_shape((x, y))
                # geo_sol = affinity.rotate(geo_sol, angle=(angle_radians - math.pi), use_radians=True)

                circular_geo.append(DrawToolShape(geo_sol))

        return circular_geo

    def util_shape(self, point):
        self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]

        if point[0] is None and point[1] is None:
            point_x = self.draw_app.x
            point_y = self.draw_app.y
        else:
            point_x = point[0]
            point_y = point[1]

        start_hor_line = ((point_x - (self.selected_dia / 2)), point_y)
        stop_hor_line = ((point_x + (self.selected_dia / 2)), point_y)
        start_vert_line = (point_x, (point_y - (self.selected_dia / 2)))
        stop_vert_line = (point_x, (point_y + (self.selected_dia / 2)))

        return MultiLineString([(start_hor_line, stop_hor_line), (start_vert_line, stop_vert_line)])

    def make(self):
        self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]
        self.geometry = []
        geo = None

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        # add the point to drills if the diameter is a key in the dict, if not, create it add the drill location
        # to the value, as a list of itself
        if self.selected_dia not in self.draw_app.points_edit:
            self.draw_app.points_edit[self.selected_dia] = []
        for i in range(self.drill_array_size):
            self.draw_app.points_edit[self.selected_dia].append(self.points)

        self.draw_app.current_storage = self.draw_app.storage_dict[self.selected_dia]

        if self.drill_array == 'linear':   # 'Linear'
            for item in range(self.drill_array_size):
                if self.drill_axis == 'X':
                    geo = self.util_shape(((self.points[0] + (self.drill_pitch * item)), self.points[1]))
                if self.drill_axis == 'Y':
                    geo = self.util_shape((self.points[0], (self.points[1] + (self.drill_pitch * item))))
                if self.drill_axis == 'A':
                    x_adj = self.drill_pitch * math.cos(math.radians(self.drill_linear_angle))
                    y_adj = self.drill_pitch * math.sin(math.radians(self.drill_linear_angle))
                    geo = self.util_shape(
                        ((self.points[0] + (x_adj * item)), (self.points[1] + (y_adj * item)))
                    )

                self.geometry.append(DrawToolShape(geo))
        else:   # 'Circular'
            if (self.drill_angle * self.drill_array_size) > 360:
                self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                              _("Too many items for the selected spacing angle."))
                self.draw_app.app.jump_signal.disconnect()
                return

            radius = distance(self.destination, self.origin)
            if radius == 0:
                self.draw_app.app.inform.emit('[ERROR_NOTCL] %s' % _("Failed."))
                self.draw_app.delete_utility_geometry()
                self.draw_app.select_tool('drill_select')
                return

            if self.destination[0] < self.origin[0]:
                radius = -radius
            initial_angle = math.asin((self.destination[1] - self.origin[1]) / radius)

            circular_geo = self.circular_util_shape(radius, initial_angle)
            self.geometry += circular_geo

        self.complete = True
        self.draw_app.app.inform.emit('[success] %s' % _("Done."))
        self.draw_app.in_action = False

        self.draw_app.last_darray_type = self.ui.array_type_radio.get_value()
        self.draw_app.last_darray_size = self.ui.array_size_entry.get_value()
        self.draw_app.last_darray_lin_dir = self.ui.axis_radio.get_value()
        self.draw_app.last_darray_circ_dir = self.ui.array_dir_radio.get_value()
        self.draw_app.last_darray_pitch = self.ui.pitch_entry.get_value()
        self.draw_app.last_darray_lin_angle = self.ui.linear_angle_entry.get_value()
        self.draw_app.last_darray_circ_angle = self.ui.circular_angle_entry.get_value()
        self.draw_app.last_darray_radius = self.ui.radius_entry.get_value()

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (AttributeError, TypeError):
            pass

    def draw_cursor_data(self, pos=None, delete=False):
        if self.cursor_data_control is False:
            self.draw_app.app.plotcanvas.text_cursor.text = ""
            return

        if pos is None:
            pos = self.draw_app.snap_x, self.draw_app.snap_y

        if delete:
            if self.draw_app.app.use_3d_engine:
                self.draw_app.app.plotcanvas.text_cursor.parent = None
                self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None
            return

        if not self.points:
            self.points = self.draw_app.snap_x, self.draw_app.snap_y

        # font size
        qsettings = QtCore.QSettings("Open Source", "FlatCAM_EVO")
        if qsettings.contains("hud_font_size"):
            fsize = qsettings.value('hud_font_size', type=int)
        else:
            fsize = 8

        x = pos[0]
        y = pos[1]
        try:
            length = abs(self.ui.radius_entry.get_value())
        except IndexError:
            length = self.draw_app.app.dec_format(0.0, self.draw_app.app.decimals)

        x_dec = str(self.draw_app.app.dec_format(x, self.draw_app.app.decimals)) if x else '0.0'
        y_dec = str(self.draw_app.app.dec_format(y, self.draw_app.app.decimals)) if y else '0.0'
        length_dec = str(self.draw_app.app.dec_format(length, self.draw_app.app.decimals)) if length else '0.0'

        units = self.draw_app.app.app_units.lower()
        l1_txt = 'X:   %s [%s]' % (x_dec, units)
        l2_txt = 'Y:   %s [%s]' % (y_dec, units)
        l3_txt = 'L:   %s [%s]' % (length_dec, units)
        cursor_text = '%s\n%s\n\n%s' % (l1_txt, l2_txt, l3_txt)

        if self.draw_app.app.use_3d_engine:
            new_pos = self.draw_app.app.plotcanvas.translate_coords_2((x, y))
            x, y, __, ___ = self.draw_app.app.plotcanvas.translate_coords((new_pos[0]+30, new_pos[1]))

            # text
            self.draw_app.app.plotcanvas.text_cursor.font_size = fsize
            self.draw_app.app.plotcanvas.text_cursor.text = cursor_text
            self.draw_app.app.plotcanvas.text_cursor.pos = x, y
            self.draw_app.app.plotcanvas.text_cursor.anchors = 'left', 'top'

            if self.draw_app.app.plotcanvas.text_cursor.parent is None:
                self.draw_app.app.plotcanvas.text_cursor.parent = self.draw_app.app.plotcanvas.view.scene

    def on_key(self, key):
        key_modifier = QtWidgets.QApplication.keyboardModifiers()

        if key_modifier == QtCore.Qt.KeyboardModifier.ShiftModifier:
            mod_key = 'Shift'
        elif key_modifier == QtCore.Qt.KeyboardModifier.ControlModifier:
            mod_key = 'Control'
        else:
            mod_key = None

        if mod_key is None:
            # Toggle Drill Array Direction
            if key == QtCore.Qt.Key.Key_Space:
                if self.ui.axis_radio.get_value() == 'X':
                    self.ui.axis_radio.set_value('Y')
                elif self.ui.axis_radio.get_value() == 'Y':
                    self.ui.axis_radio.set_value('A')
                elif self.ui.axis_radio.get_value() == 'A':
                    self.ui.axis_radio.set_value('X')

                # ## Utility geometry (animated)
                self.draw_app.update_utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y))

            if key == 'C' or key == QtCore.Qt.Key.Key_C:
                self.cursor_data_control = not self.cursor_data_control

            # Jump to coords
            if key == QtCore.Qt.Key.Key_J or key == 'J':
                self.draw_app.app.on_jump_to()

    def add_drill_array(self, array_pos):
        self.drill_radius = self.ui.radius_entry.get_value()
        self.drill_array = self.ui.array_type_radio.get_value()

        curr_pos = self.draw_app.app.geo_editor.snap(array_pos[0], array_pos[1])
        self.draw_app.snap_x = curr_pos[0]
        self.draw_app.snap_y = curr_pos[1]

        self.points = [self.draw_app.snap_x, self.draw_app.snap_y]
        self.origin = [self.draw_app.snap_x, self.draw_app.snap_y]
        self.destination = ((self.origin[0] + self.drill_radius), self.origin[1])
        self.flag_for_circ_array = True
        self.make()

        if self.draw_app.current_storage is not None:
            self.draw_app.on_exc_shape_complete(self.draw_app.current_storage)
            self.draw_app.build_ui()

        if self.draw_app.active_tool.complete:
            self.draw_app.on_shape_complete()

        self.draw_app.select_tool("drill_select")

        self.draw_app.clicked_pos = curr_pos

    def on_add_drill_array(self):
        x = self.ui.x_entry.get_value()
        y = self.ui.y_entry.get_value()
        self.add_drill_array(array_pos=(x, y))

    def clean_up(self):
        self.draw_app.selected.clear()
        self.draw_app.ui.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        if self.draw_app.app.use_3d_engine:
            self.draw_app.app.plotcanvas.text_cursor.parent = None
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class SlotAdd(FCShapeTool):
    """
    Resulting type: Polygon
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'slot_add'
        self.draw_app = draw_app
        self.app = self.draw_app.app
        self.steps_per_circ = self.draw_app.app.options["geometry_circle_steps"]
        self.half_height = 0.0
        self.half_width = 0.0

        self.selected_dia = None

        self.cursor_data_control = True

        try:
            self.draw_app.app.inform.emit(_("Click to place ..."))
            self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]

            # as a visual marker, select again in tooltable the actual tool that we are using
            # remember that it was deselected when clicking on canvas
            item = self.draw_app.ui.tools_table_exc.item((self.draw_app.last_tool_selected - 1), 1)
            self.draw_app.ui.tools_table_exc.setCurrentItem(item)
        except KeyError:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' % _("To add a slot first select a tool"))
            self.draw_app.select_tool("drill_select")
            return

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass
        self.cursor = QtGui.QCursor(QtGui.QPixmap(self.draw_app.app.resource_location + '/aero_slot.png'))
        QtGui.QGuiApplication.setOverrideCursor(self.cursor)

        self.radius = float(self.selected_dia / 2.0)

        # #############################################################################################################
        # Plugin UI
        # #############################################################################################################
        self.slot_tool = ExcSlotEditorTool(self.app, self.draw_app, plugin_name=_("Slot"))
        self.ui = self.slot_tool.ui
        self.slot_tool.run()

        geo = self.utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y))
        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            self.draw_app.draw_utility_geometry(geo=geo)

        if self.app.use_3d_engine:
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = self.draw_cursor_data
        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        self.slot_tool.length = self.draw_app.last_length
        if not self.draw_app.snap_x:
            self.draw_app.snap_x = 0.0
        if not self.draw_app.snap_y:
            self.draw_app.snap_y = 0.0

        self.app.ui.notebook.setTabText(2, _("Slot"))
        if self.app.ui.splitter.sizes()[0] == 0:
            self.app.ui.splitter.setSizes([1, 1])

        self.points = deepcopy(self.draw_app.clicked_pos) if \
            self.draw_app.clicked_pos and self.draw_app.clicked_pos[0] and self.draw_app.clicked_pos[1] else (0.0, 0.0)
        self.slot_point = None

        self.set_plugin_ui()

        # Signals
        try:
            self.ui.add_btn.clicked.disconnect()
        except (AttributeError, TypeError):
            pass
        self.ui.add_btn.clicked.connect(self.on_add_slot)

        self.draw_app.app.inform.emit(_("Click to place ..."))

    def set_plugin_ui(self):
        self.ui.slot_length_entry.set_value(self.draw_app.last_slot_length)
        self.ui.slot_direction_radio.set_value(self.draw_app.last_slot_direction)
        self.ui.on_slot_angle_radio()
        self.ui.slot_angle_spinner.set_value(self.draw_app.last_slot_angle)

        curr_row = self.draw_app.ui.tools_table_exc.currentRow()
        tool_dia = float(self.draw_app.ui.tools_table_exc.item(curr_row, 1).text())
        self.ui.dia_entry.set_value(tool_dia)
        self.ui.x_entry.set_value(float(self.draw_app.snap_x))
        self.ui.y_entry.set_value(float(self.draw_app.snap_y))

    def click(self, point):
        self.slot_point = point
        self.draw_app.last_length = self.slot_tool.length
        self.ui.x_entry.set_value(float(self.draw_app.snap_x))
        self.ui.y_entry.set_value(float(self.draw_app.snap_y))
        self.make()
        return "Done."

    def utility_geometry(self, data=None):
        geo_data = self.util_shape(data)
        return DrawToolUtilityShape(geo_data) if geo_data else None

    def util_shape(self, point):
        # updating values here allows us to change the aperture on the fly, after the Tool has been started
        self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]
        self.radius = float(self.selected_dia / 2.0)
        self.steps_per_circ = self.draw_app.app.options["geometry_circle_steps"]

        slot_length = float(self.ui.slot_length_entry.get_value())
        slot_angle = float(self.ui.slot_angle_spinner.get_value())
        if self.ui.slot_direction_radio.get_value() == 'X':
            self.half_width = slot_length / 2.0
            self.half_height = self.radius
        else:
            self.half_width = self.radius
            self.half_height = slot_length / 2.0

        if point[0] is None and point[1] is None:
            point_x = self.draw_app.x
            point_y = self.draw_app.y
        else:
            point_x = point[0]
            point_y = point[1]

        geo = []
        if self.half_height > self.half_width:
            p1 = (point_x - self.half_width, point_y - self.half_height + self.half_width)
            p2 = (point_x + self.half_width, point_y - self.half_height + self.half_width)
            p3 = (point_x + self.half_width, point_y + self.half_height - self.half_width)
            p4 = (point_x - self.half_width, point_y + self.half_height - self.half_width)

            down_center = [point_x, point_y - self.half_height + self.half_width]
            d_start_angle = math.pi
            d_stop_angle = 0.0
            down_arc = arc(down_center, self.half_width, d_start_angle, d_stop_angle, 'ccw', self.steps_per_circ)

            up_center = [point_x, point_y + self.half_height - self.half_width]
            u_start_angle = 0.0
            u_stop_angle = math.pi
            up_arc = arc(up_center, self.half_width, u_start_angle, u_stop_angle, 'ccw', self.steps_per_circ)

            geo.append(p1)
            for pt in down_arc:
                geo.append(pt)
            geo.append(p2)
            geo.append(p3)
            for pt in up_arc:
                geo.append(pt)
            geo.append(p4)

            if self.ui.slot_direction_radio.get_value() == 'A':
                return rotate(geom=Polygon(geo), angle=-slot_angle)
            else:
                return Polygon(geo)
        else:
            p1 = (point_x - self.half_width + self.half_height, point_y - self.half_height)
            p2 = (point_x + self.half_width - self.half_height, point_y - self.half_height)
            p3 = (point_x + self.half_width - self.half_height, point_y + self.half_height)
            p4 = (point_x - self.half_width + self.half_height, point_y + self.half_height)

            left_center = [point_x - self.half_width + self.half_height, point_y]
            d_start_angle = math.pi / 2
            d_stop_angle = 1.5 * math.pi
            left_arc = arc(left_center, self.half_height, d_start_angle, d_stop_angle, 'ccw', self.steps_per_circ)

            right_center = [point_x + self.half_width - self.half_height, point_y]
            u_start_angle = 1.5 * math.pi
            u_stop_angle = math.pi / 2
            right_arc = arc(right_center, self.half_height, u_start_angle, u_stop_angle, 'ccw', self.steps_per_circ)

            geo.append(p1)
            geo.append(p2)
            for pt in right_arc:
                geo.append(pt)
            geo.append(p3)
            geo.append(p4)
            for pt in left_arc:
                geo.append(pt)

            return Polygon(geo)

    def make(self):
        if self.slot_point is None:
            self.slot_point = (self.draw_app.snap_x, self.draw_app.snap_y)
        self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        # add the point to drills/slots if the diameter is a key in the dict, if not, create it add the drill location
        # to the value, as a list of itself
        if self.selected_dia in self.draw_app.slot_points_edit:
            self.draw_app.slot_points_edit[self.selected_dia].append(self.slot_point)
        else:
            self.draw_app.slot_points_edit[self.selected_dia] = [self.slot_point]

        self.draw_app.current_storage = self.draw_app.storage_dict[self.selected_dia]
        try:
            self.geometry = DrawToolShape(self.util_shape(self.slot_point))
        except Exception as e:
            log.error("SlotAdd.make() --> %s" % str(e))
        self.draw_app.in_action = False
        self.complete = True

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass

        self.draw_app.last_slot_length = self.ui.slot_length_entry.get_value()
        self.draw_app.last_slot_direction = self.ui.slot_direction_radio.get_value()
        self.draw_app.last_slot_angle = self.ui.slot_angle_spinner.get_value()

        self.draw_app.app.inform.emit('[success] %s' % _("Done."))

    def draw_cursor_data(self, pos=None, delete=False):
        if self.cursor_data_control is False:
            self.draw_app.app.plotcanvas.text_cursor.text = ""
            return

        if pos is None:
            pos = self.draw_app.snap_x, self.draw_app.snap_y

        if delete:
            if self.draw_app.app.use_3d_engine:
                self.draw_app.app.plotcanvas.text_cursor.parent = None
                self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None
            return

        if not self.points:
            self.points = self.draw_app.snap_x, self.draw_app.snap_y

        # font size
        qsettings = QtCore.QSettings("Open Source", "FlatCAM_EVO")
        if qsettings.contains("hud_font_size"):
            fsize = qsettings.value('hud_font_size', type=int)
        else:
            fsize = 8

        x = pos[0]
        y = pos[1]
        try:
            length = abs(np.sqrt((x - self.points[0]) ** 2 + (y - self.points[1]) ** 2))
        except IndexError:
            length = self.draw_app.app.dec_format(0.0, self.draw_app.app.decimals)

        x_dec = str(self.draw_app.app.dec_format(x, self.draw_app.app.decimals)) if x else '0.0'
        y_dec = str(self.draw_app.app.dec_format(y, self.draw_app.app.decimals)) if y else '0.0'
        length_dec = str(self.draw_app.app.dec_format(length, self.draw_app.app.decimals)) if length else '0.0'

        units = self.draw_app.app.app_units.lower()
        l1_txt = 'X:   %s [%s]' % (x_dec, units)
        l2_txt = 'Y:   %s [%s]' % (y_dec, units)
        l3_txt = 'L:   %s [%s]' % (length_dec, units)
        cursor_text = '%s\n%s\n\n%s' % (l1_txt, l2_txt, l3_txt)

        if self.draw_app.app.use_3d_engine:
            new_pos = self.draw_app.app.plotcanvas.translate_coords_2((x, y))
            x, y, __, ___ = self.draw_app.app.plotcanvas.translate_coords((new_pos[0]+30, new_pos[1]))

            # text
            self.draw_app.app.plotcanvas.text_cursor.font_size = fsize
            self.draw_app.app.plotcanvas.text_cursor.text = cursor_text
            self.draw_app.app.plotcanvas.text_cursor.pos = x, y
            self.draw_app.app.plotcanvas.text_cursor.anchors = 'left', 'top'

            if self.draw_app.app.plotcanvas.text_cursor.parent is None:
                self.draw_app.app.plotcanvas.text_cursor.parent = self.draw_app.app.plotcanvas.view.scene

    def on_key(self, key):
        # Jump to coords
        if key == QtCore.Qt.Key.Key_J or key == 'J':
            self.draw_app.app.on_jump_to()

        # Toggle Pad Direction
        if key == QtCore.Qt.Key.Key_Space:
            if self.ui.slot_direction_radio.get_value() == 'X':
                self.ui.slot_direction_radio.set_value('Y')
            elif self.ui.slot_direction_radio.get_value() == 'Y':
                self.ui.slot_direction_radio.set_value('A')
            elif self.ui.slot_direction_radio.get_value() == 'A':
                self.ui.slot_direction_radio.set_value('X')

            # ## Utility geometry (animated)
            self.draw_app.update_utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y))

        if key in [str(i) for i in range(10)] + ['.', ',', '+', '-', '/', '*'] or \
                key in [QtCore.Qt.Key.Key_0, QtCore.Qt.Key.Key_0, QtCore.Qt.Key.Key_1, QtCore.Qt.Key.Key_2,
                        QtCore.Qt.Key.Key_3, QtCore.Qt.Key.Key_4, QtCore.Qt.Key.Key_5, QtCore.Qt.Key.Key_6,
                        QtCore.Qt.Key.Key_7, QtCore.Qt.Key.Key_8, QtCore.Qt.Key.Key_9, QtCore.Qt.Key.Key_Minus,
                        QtCore.Qt.Key.Key_Plus, QtCore.Qt.Key.Key_Comma, QtCore.Qt.Key.Key_Period,
                        QtCore.Qt.Key.Key_Slash, QtCore.Qt.Key.Key_Asterisk]:
            try:
                # VisPy keys
                if self.slot_tool.length == self.draw_app.last_length:
                    self.slot_tool.length = str(key.name)
                else:
                    self.slot_tool.length = str(self.slot_tool.length) + str(key.name)
            except AttributeError:
                # Qt keys
                if self.slot_tool.length == self.draw_app.last_length:
                    self.slot_tool.length = chr(key)
                else:
                    self.slot_tool.length = str(self.slot_tool.length) + chr(key)

        if key == 'Enter' or key == QtCore.Qt.Key.Key_Return or key == QtCore.Qt.Key.Key_Enter:
            if self.slot_tool.length != 0:
                target_length = self.slot_tool.length
                if target_length is None:
                    self.slot_tool.length = 0.0
                    return _("Failed.")

                first_pt = self.ui.x_entry.get_value(), self.ui.y_entry.get_value()
                last_pt = self.draw_app.snap_x, self.draw_app.snap_y

                seg_length = math.sqrt((last_pt[0] - first_pt[0])**2 + (last_pt[1] - first_pt[1])**2)
                if seg_length == 0.0:
                    return
                try:
                    new_x = first_pt[0] + (last_pt[0] - first_pt[0]) / seg_length * target_length
                    new_y = first_pt[1] + (last_pt[1] - first_pt[1]) / seg_length * target_length
                except ZeroDivisionError as err:
                    self.clean_up()
                    return '[ERROR_NOTCL] %s %s' % (_("Failed."), str(err).capitalize())

                if first_pt != (new_x, new_y):
                    self.draw_app.app.on_jump_to(custom_location=(new_x, new_y), fit_center=False)
                    self.add_slot(slot_pos=(new_x, new_y))

        if key == 'C' or key == QtCore.Qt.Key.Key_C:
            self.cursor_data_control = not self.cursor_data_control

    def add_slot(self, slot_pos):
        curr_pos = self.draw_app.app.geo_editor.snap(slot_pos[0], slot_pos[1])
        self.draw_app.snap_x = curr_pos[0]
        self.draw_app.snap_y = curr_pos[1]

        self.draw_app.on_canvas_click_left_handler(curr_pos)
        if self.draw_app.active_tool.complete:
            self.draw_app.on_shape_complete()

        self.slot_point = curr_pos
        self.draw_app.clicked_pos = curr_pos

    def on_add_slot(self):
        x = self.ui.x_entry.get_value()
        y = self.ui.y_entry.get_value()
        self.add_slot(slot_pos=(x, y))

    def clean_up(self):
        self.draw_app.selected.clear()
        self.draw_app.ui.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        if self.draw_app.app.use_3d_engine:
            self.draw_app.app.plotcanvas.text_cursor.parent = None
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class SlotArray(FCShapeTool):
    """
    Resulting type: MultiPolygon
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'slot_array'
        self.draw_app = draw_app
        self.app = self.draw_app.app

        self.selected_dia = None

        self.steps_per_circ = self.draw_app.app.options["geometry_circle_steps"]

        self.half_width = 0.0
        self.half_height = 0.0

        self.array_radius = 0.0
        self.slot_axis = 'X'
        self.slot_array = 'linear'     # 'linear'
        self.slot_array_size = None
        self.slot_pitch = None
        self.slot_linear_angle = None

        self.slot_angle = None
        self.slot_direction = None
        self.slot_radius = None

        self.origin = None
        self.destination = None
        self.flag_for_circ_array = None

        self.last_dx = 0
        self.last_dy = 0

        self.pt = []

        self.cursor_data_control = True

        try:
            self.draw_app.app.inform.emit(_("Click to place ..."))
            self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]
            # as a visual marker, select again in tooltable the actual tool that we are using
            # remember that it was deselected when clicking on canvas
            item = self.draw_app.ui.tools_table_exc.item((self.draw_app.last_tool_selected - 1), 1)
            self.draw_app.ui.tools_table_exc.setCurrentItem(item)
        except KeyError:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                          _("To add an Slot Array first select a tool in Tool Table"))
            return
        self.radius = float(self.selected_dia / 2.0)

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass
        self.cursor = QtGui.QCursor(QtGui.QPixmap(self.draw_app.app.resource_location + '/aero_array.png'))
        QtGui.QGuiApplication.setOverrideCursor(self.cursor)

        # #############################################################################################################
        # Plugin UI
        # #############################################################################################################
        self.sarray_tool = ExcSlotArrayEditorTool(self.app, self.draw_app, plugin_name=_("Slot Array"))
        self.ui = self.sarray_tool.ui
        self.sarray_tool.run()

        geo = self.utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y), static=True)
        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            self.draw_app.draw_utility_geometry(geo=geo)

        if self.app.use_3d_engine:
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = self.draw_cursor_data
        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        if not self.draw_app.snap_x:
            self.draw_app.snap_x = 0.0
        if not self.draw_app.snap_y:
            self.draw_app.snap_y = 0.0

        self.app.ui.notebook.setTabText(2, _("Slot Array"))
        if self.app.ui.splitter.sizes()[0] == 0:
            self.app.ui.splitter.setSizes([1, 1])

        self.set_plugin_ui()

        # Signals
        try:
            self.ui.add_btn.clicked.disconnect()
        except (AttributeError, TypeError):
            pass
        self.ui.add_btn.clicked.connect(self.on_add_slot_array)

        # self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

    def set_plugin_ui(self):
        curr_row = self.draw_app.ui.tools_table_exc.currentRow()
        tool_dia = float(self.draw_app.ui.tools_table_exc.item(curr_row, 1).text())
        self.ui.dia_entry.set_value(tool_dia)
        self.ui.x_entry.set_value(float(self.draw_app.snap_x))
        self.ui.y_entry.set_value(float(self.draw_app.snap_y))

        # Slot set-up
        self.ui.slot_length_entry.set_value(self.draw_app.last_slot_length)
        self.ui.slot_direction_radio.set_value(self.draw_app.last_slot_direction)
        self.ui.on_slot_angle_radio()
        self.ui.slot_angle_entry.set_value(self.draw_app.last_slot_angle)

        # Slot Array set-up
        self.ui.array_type_radio.set_value(self.draw_app.last_sarray_type)
        self.ui.on_array_type_radio(val=self.ui.array_type_radio.get_value())

        self.ui.array_size_entry.set_value(self.draw_app.last_sarray_size)
        self.ui.array_axis_radio.set_value(self.draw_app.last_sarray_lin_dir)
        self.ui.array_pitch_entry.set_value(self.draw_app.last_sarray_pitch)
        self.ui.array_linear_angle_entry.set_value(self.draw_app.last_sarray_lin_angle)
        self.ui.array_direction_radio.set_value(self.draw_app.last_sarray_circ_dir)
        self.ui.array_angle_entry.set_value(self.draw_app.last_sarray_circ_angle)
        self.ui.radius_entry.set_value(self.draw_app.last_sarray_radius)

        self.ui.on_slot_array_linear_angle_radio()

    def click(self, point):
        self.ui.x_entry.set_value(float(self.draw_app.snap_x))
        self.ui.y_entry.set_value(float(self.draw_app.snap_y))

        if self.slot_array == 'linear':    # 'Linear'
            self.make()
            return
        else:   # 'Circular'
            if self.flag_for_circ_array is None:
                self.draw_app.in_action = True
                self.pt.append(point)

                self.flag_for_circ_array = True
                self.set_origin(point)
                self.draw_app.app.inform.emit(_("Click on the Circular Array Start position"))
            else:
                self.destination = point
                self.make()
                self.flag_for_circ_array = None
                return

    def set_origin(self, origin):
        self.origin = origin

    def utility_geometry(self, data=None, static=None):
        self.slot_axis = self.ui.array_axis_radio.get_value()
        self.slot_direction = self.ui.array_direction_radio.get_value()
        self.slot_array = self.ui.array_type_radio.get_value()

        self.slot_array_size = int(self.ui.array_size_entry.get_value())
        self.slot_pitch = float(self.ui.array_pitch_entry.get_value())
        self.slot_linear_angle = float(self.ui.array_linear_angle_entry.get_value())
        self.slot_angle = float(self.ui.array_angle_entry.get_value())

        if self.slot_array == 'linear':    # 'Linear'
            if data[0] is None and data[1] is None:
                dx = self.draw_app.x
                dy = self.draw_app.y
            else:
                dx = data[0]
                dy = data[1]

            geo_el_list = []
            geo_el = []
            self.points = [dx, dy]

            for item in range(self.slot_array_size):
                if self.slot_axis == 'X':
                    geo_el = self.util_shape(((dx + (self.slot_pitch * item)), dy))
                if self.slot_axis == 'Y':
                    geo_el = self.util_shape((dx, (dy + (self.slot_pitch * item))))
                if self.slot_axis == 'A':
                    x_adj = self.slot_pitch * math.cos(math.radians(self.slot_linear_angle))
                    y_adj = self.slot_pitch * math.sin(math.radians(self.slot_linear_angle))
                    geo_el = self.util_shape(
                        ((dx + (x_adj * item)), (dy + (y_adj * item)))
                    )

                if static is None or static is False:
                    geo_el = translate(geo_el, xoff=(dx - self.last_dx), yoff=(dy - self.last_dy))
                geo_el_list.append(geo_el)

            self.last_dx = dx
            self.last_dy = dy
            return DrawToolUtilityShape(geo_el_list)
        else:   # 'Circular'
            if data[0] is None and data[1] is None:
                cdx = self.draw_app.x
                cdy = self.draw_app.y
            else:
                cdx = data[0]
                cdy = data[1]

            # if len(self.pt) > 0:
            #     temp_points = [x for x in self.pt]
            #     temp_points.append([cdx, cdy])
            #     return DrawToolUtilityShape(LineString(temp_points))

            utility_list = []

            try:
                radius = distance((cdx, cdy), self.origin)
            except Exception:
                radius = 0
            if radius == 0:
                self.draw_app.delete_utility_geometry()
            self.ui.radius_entry.set_value(radius)

            if len(self.pt) >= 1 and radius > 0:
                try:
                    if cdx < self.origin[0]:
                        radius = -radius

                    # draw the temp geometry
                    initial_angle = math.asin((cdy - self.origin[1]) / radius)

                    temp_circular_geo = self.circular_util_shape(radius, initial_angle)

                    # draw the line
                    temp_points = [x for x in self.pt]
                    temp_points.append([cdx, cdy])
                    temp_line = LineString(temp_points)

                    for geo_shape in temp_circular_geo:
                        utility_list.append(geo_shape.geo)
                    utility_list.append(temp_line)

                    return DrawToolUtilityShape(utility_list)
                except Exception as e:
                    log.error("SlotArray.utility_geometry -- circular -> %s" % str(e))

    def circular_util_shape(self, radius, angle):
        self.slot_direction = self.ui.array_direction_radio.get_value()
        self.slot_angle = self.ui.array_angle_entry.get_value()
        self.slot_array_size = self.ui.array_size_entry.get_value()

        circular_geo = []
        if self.slot_direction == 'CW':
            for i in range(self.slot_array_size):
                angle_radians = math.radians(self.slot_angle * i)
                x = self.origin[0] + radius * math.cos(-angle_radians + angle)
                y = self.origin[1] + radius * math.sin(-angle_radians + angle)

                geo_sol = self.util_shape((x, y))
                geo_sol = rotate(geo_sol, angle=(math.pi - angle_radians + angle), use_radians=True)

                circular_geo.append(DrawToolShape(geo_sol))
        else:
            for i in range(self.slot_array_size):
                angle_radians = math.radians(self.slot_angle * i)
                x = self.origin[0] + radius * math.cos(angle_radians + angle)
                y = self.origin[1] + radius * math.sin(angle_radians + angle)

                geo_sol = self.util_shape((x, y))
                geo_sol = rotate(geo_sol, angle=(angle_radians + angle - math.pi), use_radians=True)

                circular_geo.append(DrawToolShape(geo_sol))

        return circular_geo

    def util_shape(self, point):
        # updating values here allows us to change the aperture on the fly, after the Tool has been started
        self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]
        self.radius = float(self.selected_dia / 2.0)
        self.steps_per_circ = self.draw_app.app.options["geometry_circle_steps"]

        slot_length = float(self.ui.slot_length_entry.get_value())
        slot_angle = float(self.ui.slot_angle_entry.get_value())

        if self.ui.slot_direction_radio.get_value() == 'X':
            self.half_width = slot_length / 2.0
            self.half_height = self.radius
        else:
            self.half_width = self.radius
            self.half_height = slot_length / 2.0

        if point[0] is None and point[1] is None:
            point_x = self.draw_app.x
            point_y = self.draw_app.y
        else:
            point_x = point[0]
            point_y = point[1]

        geo = []

        if self.half_height > self.half_width:
            p1 = (point_x - self.half_width, point_y - self.half_height + self.half_width)
            p2 = (point_x + self.half_width, point_y - self.half_height + self.half_width)
            p3 = (point_x + self.half_width, point_y + self.half_height - self.half_width)
            p4 = (point_x - self.half_width, point_y + self.half_height - self.half_width)

            down_center = [point_x, point_y - self.half_height + self.half_width]
            d_start_angle = math.pi
            d_stop_angle = 0.0
            down_arc = arc(down_center, self.half_width, d_start_angle, d_stop_angle, 'ccw', self.steps_per_circ)

            up_center = [point_x, point_y + self.half_height - self.half_width]
            u_start_angle = 0.0
            u_stop_angle = math.pi
            up_arc = arc(up_center, self.half_width, u_start_angle, u_stop_angle, 'ccw', self.steps_per_circ)

            geo.append(p1)
            for pt in down_arc:
                geo.append(pt)
            geo.append(p2)
            geo.append(p3)
            for pt in up_arc:
                geo.append(pt)
            geo.append(p4)
        else:
            p1 = (point_x - self.half_width + self.half_height, point_y - self.half_height)
            p2 = (point_x + self.half_width - self.half_height, point_y - self.half_height)
            p3 = (point_x + self.half_width - self.half_height, point_y + self.half_height)
            p4 = (point_x - self.half_width + self.half_height, point_y + self.half_height)

            left_center = [point_x - self.half_width + self.half_height, point_y]
            d_start_angle = math.pi / 2
            d_stop_angle = 1.5 * math.pi
            left_arc = arc(left_center, self.half_height, d_start_angle, d_stop_angle, 'ccw', self.steps_per_circ)

            right_center = [point_x + self.half_width - self.half_height, point_y]
            u_start_angle = 1.5 * math.pi
            u_stop_angle = math.pi / 2
            right_arc = arc(right_center, self.half_height, u_start_angle, u_stop_angle, 'ccw', self.steps_per_circ)

            geo.append(p1)
            geo.append(p2)
            for pt in right_arc:
                geo.append(pt)
            geo.append(p3)
            geo.append(p4)
            for pt in left_arc:
                geo.append(pt)

        # this function return one slot in the slot array and the following will rotate that one slot around it's
        # center if the radio value is "A".
        if self.ui.slot_direction_radio.get_value() == 'A':
            return rotate(Polygon(geo), -slot_angle)
        else:
            return Polygon(geo)

    def make(self):
        self.geometry = []
        geo = None

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        # add the point to slots if the diameter is a key in the dict, if not, create it add the drill location
        # to the value, as a list of itself
        if self.selected_dia not in self.draw_app.slot_points_edit:
            self.draw_app.slot_points_edit[self.selected_dia] = []
        for i in range(self.slot_array_size):
            self.draw_app.slot_points_edit[self.selected_dia].append(self.points)

        self.draw_app.current_storage = self.draw_app.storage_dict[self.selected_dia]

        if self.slot_array == 'linear':    # 'Linear'
            for item in range(self.slot_array_size):
                if self.slot_axis == 'X':
                    geo = self.util_shape(((self.points[0] + (self.slot_pitch * item)), self.points[1]))
                if self.slot_axis == 'Y':
                    geo = self.util_shape((self.points[0], (self.points[1] + (self.slot_pitch * item))))
                if self.slot_axis == 'A':
                    x_adj = self.slot_pitch * math.cos(math.radians(self.slot_linear_angle))
                    y_adj = self.slot_pitch * math.sin(math.radians(self.slot_linear_angle))
                    geo = self.util_shape(
                        ((self.points[0] + (x_adj * item)), (self.points[1] + (y_adj * item)))
                    )

                self.geometry.append(DrawToolShape(geo))
        else:   # 'Circular'
            if (self.slot_angle * self.slot_array_size) > 360:
                self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                              _("Too many items for the selected spacing angle."))
                try:
                    self.draw_app.app.jump_signal.disconnect()
                except (AttributeError, TypeError):
                    pass
                return

            # radius = distance(self.destination, self.origin)
            # initial_angle = math.asin((self.destination[1] - self.origin[1]) / radius)
            # for i in range(self.slot_array_size):
            #     angle_radians = math.radians(self.slot_angle * i)
            #     if self.slot_direction == 'CW':
            #         x = self.origin[0] + radius * math.cos(-angle_radians + initial_angle)
            #         y = self.origin[1] + radius * math.sin(-angle_radians + initial_angle)
            #     else:
            #         x = self.origin[0] + radius * math.cos(angle_radians + initial_angle)
            #         y = self.origin[1] + radius * math.sin(angle_radians + initial_angle)
            #
            #     geo = self.util_shape((x, y))
            #     if self.slot_direction == 'CW':
            #         geo = affinity.rotate(geo, angle=(math.pi - angle_radians), use_radians=True)
            #     else:
            #         geo = affinity.rotate(geo, angle=(angle_radians - math.pi), use_radians=True)
            #
            #     self.geometry.append(DrawToolShape(geo))

            radius = distance(self.destination, self.origin)
            if radius == 0:
                self.draw_app.app.inform.emit('[ERROR_NOTCL] %s' % _("Failed."))
                self.draw_app.delete_utility_geometry()
                self.draw_app.select_tool('drill_select')
                return

            if self.destination[0] < self.origin[0]:
                radius = -radius
            initial_angle = math.asin((self.destination[1] - self.origin[1]) / radius)

            circular_geo = self.circular_util_shape(radius, initial_angle)
            self.geometry += circular_geo

        self.complete = True
        self.draw_app.app.inform.emit('[success] %s' % _("Done."))
        self.draw_app.in_action = False

        # Slot
        self.draw_app.last_slot_length = self.ui.slot_length_entry.get_value()
        self.draw_app.last_slot_direction = self.ui.slot_direction_radio.get_value()
        self.draw_app.last_slot_angle = self.ui.slot_angle_entry.get_value()

        # Slot array
        self.draw_app.last_sarray_type = self.ui.array_type_radio.get_value()
        self.draw_app.last_sarray_size = self.ui.array_size_entry.get_value()
        self.draw_app.last_sarray_lin_dir = self.ui.array_axis_radio.get_value()
        self.draw_app.last_sarray_circ_dir = self.ui.array_direction_radio.get_value()
        self.draw_app.last_sarray_pitch = self.ui.array_pitch_entry.get_value()
        self.draw_app.last_sarray_lin_angle = self.ui.array_linear_angle_entry.get_value()
        self.draw_app.last_sarray_circ_angle = self.ui.array_angle_entry.get_value()
        self.draw_app.last_sarray_radius = self.ui.radius_entry.get_value()

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (AttributeError, TypeError):
            pass

    def draw_cursor_data(self, pos=None, delete=False):
        if self.cursor_data_control is False:
            self.draw_app.app.plotcanvas.text_cursor.text = ""
            return

        if pos is None:
            pos = self.draw_app.snap_x, self.draw_app.snap_y

        if delete:
            if self.draw_app.app.use_3d_engine:
                self.draw_app.app.plotcanvas.text_cursor.parent = None
                self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None
            return

        if not self.points:
            self.points = self.draw_app.snap_x, self.draw_app.snap_y

        # font size
        qsettings = QtCore.QSettings("Open Source", "FlatCAM_EVO")
        if qsettings.contains("hud_font_size"):
            fsize = qsettings.value('hud_font_size', type=int)
        else:
            fsize = 8

        x = pos[0]
        y = pos[1]
        try:
            length = abs(self.ui.radius_entry.get_value())
        except IndexError:
            length = self.draw_app.app.dec_format(0.0, self.draw_app.app.decimals)

        x_dec = str(self.draw_app.app.dec_format(x, self.draw_app.app.decimals)) if x else '0.0'
        y_dec = str(self.draw_app.app.dec_format(y, self.draw_app.app.decimals)) if y else '0.0'
        length_dec = str(self.draw_app.app.dec_format(length, self.draw_app.app.decimals)) if length else '0.0'

        units = self.draw_app.app.app_units.lower()
        l1_txt = 'X:   %s [%s]' % (x_dec, units)
        l2_txt = 'Y:   %s [%s]' % (y_dec, units)
        l3_txt = 'L:   %s [%s]' % (length_dec, units)
        cursor_text = '%s\n%s\n\n%s' % (l1_txt, l2_txt, l3_txt)

        if self.draw_app.app.use_3d_engine:
            new_pos = self.draw_app.app.plotcanvas.translate_coords_2((x, y))
            x, y, __, ___ = self.draw_app.app.plotcanvas.translate_coords((new_pos[0]+30, new_pos[1]))

            # text
            self.draw_app.app.plotcanvas.text_cursor.font_size = fsize
            self.draw_app.app.plotcanvas.text_cursor.text = cursor_text
            self.draw_app.app.plotcanvas.text_cursor.pos = x, y
            self.draw_app.app.plotcanvas.text_cursor.anchors = 'left', 'top'

            if self.draw_app.app.plotcanvas.text_cursor.parent is None:
                self.draw_app.app.plotcanvas.text_cursor.parent = self.draw_app.app.plotcanvas.view.scene

    def on_key(self, key):
        key_modifier = QtWidgets.QApplication.keyboardModifiers()

        if key_modifier == QtCore.Qt.KeyboardModifier.ShiftModifier:
            mod_key = 'Shift'
        elif key_modifier == QtCore.Qt.KeyboardModifier.ControlModifier:
            mod_key = 'Control'
        else:
            mod_key = None

        if mod_key == 'Control':
            # Toggle Pad Array Direction
            if key == QtCore.Qt.Key.Key_Space:
                if self.ui.array_axis_radio.get_value() == 'X':
                    self.ui.array_axis_radio.set_value('Y')
                elif self.ui.array_axis_radio.get_value() == 'Y':
                    self.ui.array_axis_radio.set_value('A')
                elif self.ui.array_axis_radio.get_value() == 'A':
                    self.ui.array_axis_radio.set_value('X')

                # ## Utility geometry (animated)
                self.draw_app.update_utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y))
        elif mod_key is None:
            if key == 'C' or key == QtCore.Qt.Key.Key_C:
                self.cursor_data_control = not self.cursor_data_control

            # Jump to coords
            if key == QtCore.Qt.Key.Key_J or key == 'J':
                self.draw_app.app.on_jump_to()

            # Toggle Pad Direction
            if key == QtCore.Qt.Key.Key_Space:
                if self.ui.slot_direction_radio.get_value() == 'X':
                    self.ui.slot_direction_radio.set_value('Y')
                elif self.ui.slot_direction_radio.get_value() == 'Y':
                    self.ui.slot_direction_radio.set_value('A')
                elif self.ui.slot_direction_radio.get_value() == 'A':
                    self.ui.slot_direction_radio.set_value('X')

                # ## Utility geometry (animated)
                self.draw_app.update_utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y))

    def add_slot_array(self, array_pos):
        self.array_radius = self.ui.radius_entry.get_value()

        self.slot_axis = self.ui.array_axis_radio.get_value()
        self.slot_direction = self.ui.array_direction_radio.get_value()
        self.slot_array = self.ui.array_type_radio.get_value()

        self.slot_array_size = int(self.ui.array_size_entry.get_value())
        self.slot_pitch = float(self.ui.array_pitch_entry.get_value())
        self.slot_linear_angle = float(self.ui.array_linear_angle_entry.get_value())
        self.slot_angle = float(self.ui.array_angle_entry.get_value())

        curr_pos = self.draw_app.app.geo_editor.snap(array_pos[0], array_pos[1])
        self.draw_app.snap_x = curr_pos[0]
        self.draw_app.snap_y = curr_pos[1]

        self.points = [self.draw_app.snap_x, self.draw_app.snap_y]
        self.origin = [self.draw_app.snap_x, self.draw_app.snap_y]
        self.destination = ((self.origin[0] + self.array_radius), self.origin[1])
        self.flag_for_circ_array = True
        self.make()

        if self.draw_app.current_storage is not None:
            self.draw_app.on_exc_shape_complete(self.draw_app.current_storage)
            self.draw_app.build_ui()

        if self.draw_app.active_tool.complete:
            self.draw_app.on_shape_complete()

        self.draw_app.select_tool("drill_select")

        self.draw_app.clicked_pos = curr_pos

    def on_add_slot_array(self):
        x = self.ui.x_entry.get_value()
        y = self.ui.y_entry.get_value()
        self.add_slot_array(array_pos=(x, y))

    def clean_up(self):
        self.draw_app.selected.clear()
        self.draw_app.ui.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        if self.draw_app.app.use_3d_engine:
            self.draw_app.app.plotcanvas.text_cursor.parent = None
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class ResizeEditorExc(FCShapeTool):
    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'drill_resize'
        self.draw_app = draw_app
        self.app = self.draw_app.app

        self.resize_dia = None
        self.points = None

        # made this a set so there are no duplicates
        self.selected_dia_set = set()

        self.current_storage = None
        self.geometry = []
        self.destination_storage = None

        self.cursor_data_control = True

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass
        # #############################################################################################################
        # Plugin UI
        # #############################################################################################################
        self.resize_tool = ExcResizeEditorTool(self.app, self.draw_app, plugin_name=_("Resize"))
        self.ui = self.resize_tool.ui
        self.resize_tool.run()

        if self.app.use_3d_engine:
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = self.draw_cursor_data
        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        if not self.draw_app.snap_x:
            self.draw_app.snap_x = 0.0
        if not self.draw_app.snap_y:
            self.draw_app.snap_y = 0.0

        self.app.ui.notebook.setTabText(2, _("Resize"))
        if self.app.ui.splitter.sizes()[0] == 0:
            self.app.ui.splitter.setSizes([1, 1])

        self.set_plugin_ui()

        # Signals
        try:
            self.ui.resize_btn.clicked.disconnect()
        except (AttributeError, TypeError):
            pass
        try:
            self.ui.res_dia_entry.editingFinished.disconnect()
        except (AttributeError, TypeError):
            pass
        self.ui.resize_btn.clicked.connect(self.on_resize)
        self.ui.res_dia_entry.editingFinished.connect(self.on_resize)

        self.draw_app.app.inform.emit(_("Click on the Drill(s) to resize ..."))

    def set_plugin_ui(self):
        # curr_row = self.draw_app.ui.tools_table_exc.currentRow()
        # tool_dia = float(self.draw_app.ui.tools_table_exc.item(curr_row, 1).text())
        # self.ui.dia_entry.set_value(tool_dia)

        self.update_diameters()

    def utility_geometry(self, data=None):
        return DrawToolUtilityShape([])

    def click_release(self, point):
        self.update_diameters()

    def update_diameters(self):
        sel_dia_list = set()
        for index in self.draw_app.ui.tools_table_exc.selectedIndexes():
            row = index.row()
            if row < 0:
                continue
            # on column 1 in tool tables we hold the diameters, and we retrieve them as strings
            # therefore below we convert to float
            dia_on_row = self.draw_app.ui.tools_table_exc.item(row, 1).text()
            if dia_on_row != '':
                sel_dia_list.add(dia_on_row)

        self.ui.dia_entry.set_value(', '.join([i for i in list(sel_dia_list)]))

    def make(self):
        self.draw_app.is_modified = True

        try:
            self.draw_app.ui.tools_table_exc.itemChanged.disconnect()
        except TypeError:
            pass

        new_dia = self.ui.res_dia_entry.get_value()
        if new_dia == 0.0:
            self.draw_app.app.inform.emit('[ERROR_NOTCL] %s' %
                                          _("Resize drill(s) failed. Please enter a diameter for resize."))
            return

        if new_dia not in self.draw_app.olddia_newdia:
            self.destination_storage = AppGeoEditor.make_storage()
            self.draw_app.storage_dict[new_dia] = self.destination_storage

            # self.olddia_newdia dict keeps the evidence on current tools diameters as keys and gets updated on values
            # each time a tool diameter is edited or added
            self.draw_app.olddia_newdia[new_dia] = new_dia
        else:
            self.destination_storage = self.draw_app.storage_dict[new_dia]

        for index in self.draw_app.ui.tools_table_exc.selectedIndexes():
            row = index.row()
            # on column 1 in tool tables we hold the diameters, and we retrieve them as strings
            # therefore below we convert to float
            dia_on_row = self.draw_app.ui.tools_table_exc.item(row, 1).text()
            self.selected_dia_set.add(float(dia_on_row))

        # since we add a new tool, we update also the intial state of the plugin_table through it's dictionary
        # we add a new entry in the tool2tooldia dict
        self.draw_app.tool2tooldia[len(self.draw_app.olddia_newdia)] = new_dia

        sel_shapes_to_be_deleted = []

        if self.selected_dia_set:
            for sel_dia in self.selected_dia_set:
                self.current_storage = self.draw_app.storage_dict[sel_dia]
                for select_shape in self.draw_app.get_selected():
                    if select_shape in self.current_storage.get_objects():

                        # add new geometry according to the new size
                        if isinstance(select_shape.geo, MultiLineString):
                            factor = new_dia / sel_dia
                            self.geometry.append(DrawToolShape(scale(select_shape.geo, xfact=factor, yfact=factor,
                                                                     origin='center')))
                        elif isinstance(select_shape.geo, Polygon):
                            # I don't have any info regarding the angle of the slot geometry, nor how thick it is or
                            # how long it is given the angle. So I will have to make an approximation because
                            # we need to conserve the slot length, we only resize the diameter for the tool
                            # Therefore scaling won't work and buffering will not work either.

                            # First we get the Linestring that is one that the original slot is built around with the
                            # tool having the diameter sel_dia
                            poly = select_shape.geo
                            xmin, ymin, xmax, ymax = poly.bounds
                            # a line that is certain to be bigger than our slot because it's the diagonal
                            # of it's bounding box
                            poly_diagonal = LineString([(xmin, ymin), (xmax, ymax)])
                            poly_centroid = poly.centroid
                            # center of the slot geometry
                            poly_center = (poly_centroid.x, poly_centroid.y)

                            # make a list of intersections with the rotated line
                            list_of_cuttings = []
                            for angle in range(0, 359, 1):
                                rot_poly_diagonal = rotate(poly_diagonal, angle=angle, origin=poly_center)
                                cut_line = rot_poly_diagonal.intersection(poly)
                                cut_line_len = cut_line.length
                                list_of_cuttings.append(
                                    (cut_line_len, cut_line)
                                )
                            # find the cut_line with the maximum length which is the LineString for which the start
                            # and stop point are the start and stop point of the slot as in the Gerber file
                            cut_line_with_max_length = max(list_of_cuttings, key=lambda i: i[0])[1]
                            # find the coordinates of this line
                            cut_line_with_max_length_coords = list(cut_line_with_max_length.coords)
                            # extract the first and last point of the line and build some buffered polygon circles
                            # around them
                            start_pt = Point(cut_line_with_max_length_coords[0])
                            stop_pt = Point(cut_line_with_max_length_coords[1])
                            start_cut_geo = start_pt.buffer(new_dia / 2)
                            stop_cut_geo = stop_pt.buffer(new_dia / 2)

                            # and we cut the above circle polygons from our line and get in this way a line around
                            # which we can build the new slot by buffering with the new tool diameter
                            new_line = cut_line_with_max_length.difference(start_cut_geo)
                            new_line = new_line.difference(stop_cut_geo)

                            # create the geometry for the resized slot by buffering with half of the
                            # new diameter value, new_dia
                            new_poly = new_line.buffer(new_dia / 2)

                            self.geometry.append(DrawToolShape(new_poly))
                        else:
                            # unexpected geometry so we cancel
                            self.draw_app.app.inform.emit('[ERROR_NOTCL] %s' % _("Cancelled."))
                            return

                        # remove the geometry with the old size
                        self.current_storage.remove(select_shape)

                        # a hack to make the plugin_table display less drills per diameter when shape(drill) is deleted
                        # self.points_edit it's only useful first time when we load the data into the storage
                        # but is still used as reference when building plugin_table in self.build_ui()
                        # the number of drills displayed in column 2 is just a len(self.points_edit) therefore
                        # deleting self.points_edit elements (doesn't matter who but just the number)
                        # solved the display issue.
                        if isinstance(select_shape.geo, MultiLineString):
                            try:
                                del self.draw_app.points_edit[sel_dia][0]
                            except KeyError:
                                # if the exception happen here then we are not dealing with drills but with slots
                                # This should not happen as the drills have MultiLineString geometry and slots have
                                # Polygon geometry
                                pass
                        if isinstance(select_shape.geo, Polygon):
                            try:
                                del self.draw_app.slot_points_edit[sel_dia][0]
                            except KeyError:
                                # if the exception happen here then we are not dealing with slots but with drills
                                # This should not happen as the drills have MultiLineString geometry and slots have
                                # Polygon geometry
                                pass

                        sel_shapes_to_be_deleted.append(select_shape)

                        # a hack to make the plugin_table display more drills/slots per diameter when shape(drill/slot)
                        # is added.
                        # self.points_edit it's only useful first time when we load the data into the storage
                        # but is still used as reference when building plugin_table in self.build_ui()
                        # the number of drills displayed in column 2 is just a len(self.points_edit) therefore
                        # deleting self.points_edit elements (doesn't matter who but just the number)
                        # solved the display issue.

                        # for drills
                        if isinstance(select_shape.geo, MultiLineString):
                            if new_dia not in self.draw_app.points_edit:
                                self.draw_app.points_edit[new_dia] = [(0, 0)]
                            else:
                                self.draw_app.points_edit[new_dia].append((0, 0))

                        # for slots
                        if isinstance(select_shape.geo, Polygon):
                            if new_dia not in self.draw_app.slot_points_edit:
                                self.draw_app.slot_points_edit[new_dia] = [(0, 0)]
                            else:
                                self.draw_app.slot_points_edit[new_dia].append((0, 0))

            for dia_key in list(self.draw_app.storage_dict.keys()):
                # if following the resize of the drills there will be no more drills for some of the tools then
                # delete those tools
                try:
                    if not self.draw_app.points_edit[dia_key]:
                        self.draw_app.on_tool_delete(dia_key)
                except KeyError:
                    # if the exception happen here then we are not dealing with drills but with slots
                    # so we try for them
                    try:
                        if not self.draw_app.slot_points_edit[dia_key]:
                            self.draw_app.on_tool_delete(dia_key)
                    except KeyError:
                        # if the exception happen here then we are not dealing with slots neither
                        # therefore something else is not OK so we return
                        self.draw_app.app.inform.emit('[ERROR_NOTCL] %s' % _("Cancelled."))
                        return

            # this simple hack is used so we can delete form self.draw_app.selected but
            # after we no longer iterate through it
            for shp in sel_shapes_to_be_deleted:
                self.draw_app.selected.remove(shp)

            # add the new geometry to storage
            self.draw_app.on_exc_shape_complete(self.destination_storage)

            self.draw_app.build_ui()
            self.draw_app.replot()

            # empty the self.geometry
            self.geometry = []

            # we reactivate the signals after the after the tool editing
            self.draw_app.ui.tools_table_exc.itemChanged.connect(self.draw_app.on_tool_edit)

            self.draw_app.app.inform.emit('[success] %s' % _("Done."))
        else:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s %s' % (_("Cancelled."), _("Nothing selected")))

        # init this set() for another use perhaps
        self.selected_dia_set = set()

        self.complete = True

        # MS: always return to the Select Tool
        self.draw_app.select_tool("drill_select")

    def on_resize(self):
        self.make()
        self.clean_up()

    def draw_cursor_data(self, pos=None, delete=False):
        if self.cursor_data_control is False:
            self.draw_app.app.plotcanvas.text_cursor.text = ""
            return

        if pos is None:
            pos = self.draw_app.snap_x, self.draw_app.snap_y

        if delete:
            if self.draw_app.app.use_3d_engine:
                self.draw_app.app.plotcanvas.text_cursor.parent = None
                self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None
            return

        if not self.points:
            self.points = self.draw_app.snap_x, self.draw_app.snap_y

        # font size
        qsettings = QtCore.QSettings("Open Source", "FlatCAM_EVO")
        if qsettings.contains("hud_font_size"):
            fsize = qsettings.value('hud_font_size', type=int)
        else:
            fsize = 8

        x = pos[0]
        y = pos[1]
        try:
            length = abs(np.sqrt((x - self.points[0]) ** 2 + (y - self.points[1]) ** 2))
        except IndexError:
            length = self.draw_app.app.dec_format(0.0, self.draw_app.app.decimals)

        x_dec = str(self.draw_app.app.dec_format(x, self.draw_app.app.decimals)) if x else '0.0'
        y_dec = str(self.draw_app.app.dec_format(y, self.draw_app.app.decimals)) if y else '0.0'
        length_dec = str(self.draw_app.app.dec_format(length, self.draw_app.app.decimals)) if length else '0.0'

        units = self.draw_app.app.app_units.lower()
        l1_txt = 'X:   %s [%s]' % (x_dec, units)
        l2_txt = 'Y:   %s [%s]' % (y_dec, units)
        l3_txt = 'L:   %s [%s]' % (length_dec, units)
        cursor_text = '%s\n%s\n\n%s' % (l1_txt, l2_txt, l3_txt)

        if self.draw_app.app.use_3d_engine:
            new_pos = self.draw_app.app.plotcanvas.translate_coords_2((x, y))
            x, y, __, ___ = self.draw_app.app.plotcanvas.translate_coords((new_pos[0]+30, new_pos[1]))

            # text
            self.draw_app.app.plotcanvas.text_cursor.font_size = fsize
            self.draw_app.app.plotcanvas.text_cursor.text = cursor_text
            self.draw_app.app.plotcanvas.text_cursor.pos = x, y
            self.draw_app.app.plotcanvas.text_cursor.anchors = 'left', 'top'

            if self.draw_app.app.plotcanvas.text_cursor.parent is None:
                self.draw_app.app.plotcanvas.text_cursor.parent = self.draw_app.app.plotcanvas.view.scene

    def on_key(self, key):
        if key == 'C' or key == QtCore.Qt.Key.Key_C:
            self.cursor_data_control = not self.cursor_data_control

    def clean_up(self):
        self.draw_app.selected.clear()
        self.draw_app.ui.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        if self.draw_app.app.use_3d_engine:
            self.draw_app.app.plotcanvas.text_cursor.parent = None
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class MoveEditorExc(FCShapeTool):
    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'drill_move'

        # self.shape_buffer = self.draw_app.shape_buffer
        self.origin = None
        self.destination = None
        self.sel_limit = self.draw_app.app.options["excellon_editor_sel_limit"]
        self.selection_shape = self.selection_bbox()
        self.selected_dia_list = []

        self.current_storage = None
        self.geometry = []

        for index in self.draw_app.ui.tools_table_exc.selectedIndexes():
            row = index.row()
            # on column 1 in tool tables we hold the diameters, and we retrieve them as strings
            # therefore below we convert to float
            dia_on_row = self.draw_app.ui.tools_table_exc.item(row, 1).text()
            self.selected_dia_list.append(float(dia_on_row))

        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        # Switch notebook to Properties page
        self.draw_app.app.ui.notebook.setCurrentWidget(self.draw_app.app.ui.properties_tab)

        if self.draw_app.launched_from_shortcuts is True:
            self.draw_app.launched_from_shortcuts = False
        else:
            if not self.draw_app.get_selected():
                self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled. Nothing selected."))
                self.draw_app.app.ui.select_drill_btn.setChecked(True)
                self.draw_app.on_tool_select('drill_select')
            else:
                self.draw_app.app.inform.emit(_("Click on reference location ..."))

    def set_origin(self, origin):
        self.origin = origin

    def click(self, point):
        if not self.draw_app.get_selected():
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled. Nothing selected."))
            return "Nothing to move."

        if self.origin is None:
            self.set_origin(point)
            self.draw_app.app.inform.emit(_("Click on target location ..."))
            return
        else:
            self.destination = point
            self.make()

            # MS: always return to the Select Tool
            self.draw_app.select_tool("drill_select")
            return

    def make(self):
        # Create new geometry
        dx = self.destination[0] - self.origin[0]
        dy = self.destination[1] - self.origin[1]
        sel_shapes_to_be_deleted = []

        for sel_dia in self.selected_dia_list:
            self.current_storage = self.draw_app.storage_dict[sel_dia]
            for select_shape in self.draw_app.get_selected():
                if select_shape in self.current_storage.get_objects():

                    self.geometry.append(DrawToolShape(translate(select_shape.geo, xoff=dx, yoff=dy)))
                    self.current_storage.remove(select_shape)
                    sel_shapes_to_be_deleted.append(select_shape)
                    self.draw_app.on_exc_shape_complete(self.current_storage)
                    self.geometry = []

            for shp in sel_shapes_to_be_deleted:
                self.draw_app.selected.remove(shp)
            sel_shapes_to_be_deleted = []

        self.draw_app.build_ui()
        self.draw_app.app.inform.emit('[success] %s' % _("Done."))
        try:
            self.draw_app.app.jump_signal.disconnect()
        except TypeError:
            pass

    def selection_bbox(self):
        geo_list = []
        for select_shape in self.draw_app.get_selected():
            if isinstance(select_shape.geo, (MultiLineString, MultiPolygon)):
                geometric_data = select_shape.geo.geoms
            else:
                geometric_data = select_shape.geo

            try:
                for g in geometric_data:
                    geo_list.append(g)
            except TypeError:
                geo_list.append(geometric_data)

        xmin, ymin, xmax, ymax = get_shapely_list_bounds(geo_list)

        pt1 = (xmin, ymin)
        pt2 = (xmax, ymin)
        pt3 = (xmax, ymax)
        pt4 = (xmin, ymax)

        return Polygon([pt1, pt2, pt3, pt4])

    def utility_geometry(self, data=None):
        """
        Temporary geometry on screen while using this tool.

        :param data:
        :return:
        """
        geo_list = []

        if self.origin is None:
            return None

        if len(self.draw_app.get_selected()) == 0:
            return None

        dx = data[0] - self.origin[0]
        dy = data[1] - self.origin[1]

        if len(self.draw_app.get_selected()) <= self.sel_limit:
            try:
                for geom in self.draw_app.get_selected():
                    geo_list.append(translate(geom.geo, xoff=dx, yoff=dy))
            except AttributeError:
                self.draw_app.select_tool('drill_select')
                self.draw_app.selected.clear()
                return
            return DrawToolUtilityShape(geo_list)
        else:
            try:
                ss_el = translate(self.selection_shape, xoff=dx, yoff=dy)
            except ValueError:
                ss_el = None
            return DrawToolUtilityShape(ss_el)

    def clean_up(self):
        self.draw_app.selected.clear()
        self.draw_app.ui.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class CopyEditorExc(FCShapeTool):
    def __init__(self, draw_app):
        FCShapeTool.__init__(self, draw_app)
        self.name = 'drill_copy'
        self.draw_app = draw_app
        self.app = self.draw_app.app
        self.storage = self.draw_app.storage_dict

        self.origin = None
        self.destination = None
        self.sel_limit = self.draw_app.app.options["excellon_editor_sel_limit"]
        self.selection_shape = self.selection_bbox()
        self.selected_dia_list = []

        self.current_storage = None
        self.geometry = []

        self.cursor_data_control = True

        for index in self.draw_app.ui.tools_table_exc.selectedIndexes():
            row = index.row()
            # on column 1 in tool tables we hold the diameters, and we retrieve them as strings
            # therefore below we convert to float
            dia_on_row = self.draw_app.ui.tools_table_exc.item(row, 1).text()
            self.selected_dia_list.append(float(dia_on_row))

        # store here the utility geometry, so we can use it on the last step
        self.util_geo = None

        if not self.draw_app.get_selected():
            self.has_selection = False
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s %s' % (_("Cancelled."), _("Nothing selected.")))
            self.draw_app.app.ui.select_drill_btn.setChecked(True)
            self.draw_app.on_tool_select('drill_select')
        else:
            self.has_selection = True
            self.draw_app.app.inform.emit(_("Click on reference location ..."))

        if self.app.use_3d_engine:
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = self.draw_cursor_data

        self.copy_tool = ExcCopyEditorTool(self.app, self.draw_app, plugin_name=_("Copy"))
        self.ui = self.copy_tool.ui
        self.copy_tool.run()

        self.app.ui.notebook.setTabText(2, _("Copy"))
        if self.draw_app.app.ui.splitter.sizes()[0] == 0:
            self.draw_app.app.ui.splitter.setSizes([1, 1])

        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

    def set_origin(self, origin):
        self.draw_app.app.inform.emit(_("Click on destination point ..."))
        self.origin = origin

    def click(self, point):
        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass
        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        if self.has_selection is False:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s %s' % (_("Cancelled."), _(" Nothing selected.")))
            return "Nothing to move."

        if self.origin is None:
            self.set_origin(point)
            self.draw_app.app.inform.emit(_("Click on target location ..."))
            return
        else:
            self.destination = point
            self.make()

            # MS: always return to the Select Tool
            self.draw_app.select_tool("drill_select")
            return

    def make(self):
        # Create new geometry
        # dx = self.destination[0] - self.origin[0]
        # dy = self.destination[1] - self.origin[1]
        sel_shapes_to_be_deleted = []

        if len(self.draw_app.get_selected()) > self.sel_limit:
            self.util_geo = self.array_util_geometry((self.destination[0], self.destination[1]))

        # when doing circular array we remove the last geometry item in the list because it is the temp_line
        if self.ui.mode_radio.get_value() == 'a' and \
                self.ui.array_type_radio.get_value() == 'circular':
            del self.util_geo.geo[-1]

        self.geometry = [DrawToolShape(deepcopy(shp)) for shp in self.util_geo.geo]

        for sel_dia in self.selected_dia_list:
            self.current_storage = self.draw_app.storage_dict[sel_dia]
            for select_shape in self.draw_app.get_selected():
                if select_shape in self.current_storage.get_objects():

                    # Add some fake drills into the self.draw_app.points_edit to update the drill count in tool table
                    # This may fail if we copy slots.
                    try:
                        self.draw_app.points_edit[sel_dia].append((0, 0))
                    except KeyError:
                        pass

                    # add some fake slots into the self.draw_app.slots_points_edit
                    # to update the slot count in tool table
                    # This may fail if we copy drills.
                    try:
                        self.draw_app.slot_points_edit[sel_dia].append((0, 0))
                    except KeyError:
                        pass

                    sel_shapes_to_be_deleted.append(select_shape)
                    self.draw_app.on_exc_shape_complete(self.current_storage)
                    self.geometry = []

            for shp in sel_shapes_to_be_deleted:
                self.draw_app.selected.remove(shp)
            sel_shapes_to_be_deleted = []

        self.complete = True
        self.origin = None
        self.draw_cursor_data(delete=True)

        self.draw_app.build_ui()
        self.draw_app.app.inform.emit('[success] %s' % _("Done."))
        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass

    def selection_bbox(self):
        geo_list = []
        for select_shape in self.draw_app.get_selected():
            if isinstance(select_shape.geo, (MultiLineString, MultiPolygon)):
                geometric_data = select_shape.geo.geoms
            else:
                geometric_data = select_shape.geo

            try:
                for g in geometric_data:
                    geo_list.append(g)
            except TypeError:
                geo_list.append(geometric_data)

        xmin, ymin, xmax, ymax = get_shapely_list_bounds(geo_list)

        pt1 = (xmin, ymin)
        pt2 = (xmax, ymin)
        pt3 = (xmax, ymax)
        pt4 = (xmin, ymax)

        return Polygon([pt1, pt2, pt3, pt4])

    def utility_geometry(self, data=None):
        """
        Temporary geometry on screen while using this tool.

        :param data:
        :return:
        """
        geo_list = []

        if self.origin is None:
            return None

        if len(self.draw_app.get_selected()) == 0:
            return None

        dx = data[0] - self.origin[0]
        dy = data[1] - self.origin[1]

        if len(self.draw_app.get_selected()) <= self.sel_limit:
            copy_mode = self.ui.mode_radio.get_value()
            if copy_mode == 'n':
                try:
                    for geom in self.draw_app.get_selected():
                        geo_list.append(translate(geom.geo, xoff=dx, yoff=dy))
                except AttributeError:
                    self.draw_app.select_tool('drill_select')
                    self.draw_app.selected.clear()
                    return
                self.util_geo = DrawToolUtilityShape(geo_list)
            else:
                self.util_geo = self.array_util_geometry((dx, dy))
        else:
            try:
                ss_el = translate(self.selection_shape, xoff=dx, yoff=dy)
            except ValueError:
                ss_el = None
            self.util_geo = DrawToolUtilityShape(ss_el)

        return self.util_geo

    def array_util_geometry(self, pos, static=None):
        array_type = self.ui.array_type_radio.get_value()      # 'linear', '2D', 'circular'

        if array_type == 'linear':  # 'Linear'
            return self.linear_geo(pos, static)
        elif array_type == '2D':
            return self.dd_geo(pos)
        elif array_type == 'circular':  # 'Circular'
            return self.circular_geo(pos)

    def linear_geo(self, pos, static):
        axis = self.ui.axis_radio.get_value()  # X, Y or A
        pitch = float(self.ui.pitch_entry.get_value())
        linear_angle = float(self.ui.linear_angle_spinner.get_value())
        array_size = int(self.ui.array_size_entry.get_value())

        if pos[0] is None and pos[1] is None:
            dx = self.draw_app.x
            dy = self.draw_app.y
        else:
            dx = pos[0]
            dy = pos[1]

        geo_list = []
        self.points = [(dx, dy)]

        for item in range(array_size):
            if axis == 'X':
                new_pos = ((dx + (pitch * item)), dy)
            elif axis == 'Y':
                new_pos = (dx, (dy + (pitch * item)))
            else:  # 'A'
                x_adj = pitch * math.cos(math.radians(linear_angle))
                y_adj = pitch * math.sin(math.radians(linear_angle))
                new_pos = ((dx + (x_adj * item)), (dy + (y_adj * item)))

            for g in self.draw_app.get_selected():
                if static is None or static is False:
                    geo_list.append(translate(g.geo, xoff=new_pos[0], yoff=new_pos[1]))
                else:
                    geo_list.append(g.geo)
        return DrawToolUtilityShape(geo_list)

    def dd_geo(self, pos):
        trans_geo = []
        array_2d_type = self.ui.placement_radio.get_value()

        rows = self.ui.rows.get_value()
        columns = self.ui.columns.get_value()

        spacing_rows = self.ui.spacing_rows.get_value()
        spacing_columns = self.ui.spacing_columns.get_value()

        off_x = self.ui.offsetx_entry.get_value()
        off_y = self.ui.offsety_entry.get_value()

        geo_source = [s.geo for s in self.draw_app.get_selected()]

        def geo_bounds(geo: (BaseGeometry, list)):
            minx = np.Inf
            miny = np.Inf
            maxx = -np.Inf
            maxy = -np.Inf

            if type(geo) == list:
                for shp in geo:
                    minx_, miny_, maxx_, maxy_ = geo_bounds(shp)
                    minx = min(minx, minx_)
                    miny = min(miny, miny_)
                    maxx = max(maxx, maxx_)
                    maxy = max(maxy, maxy_)
                return minx, miny, maxx, maxy
            else:
                # it's an object, return its bounds
                return geo.bounds

        xmin, ymin, xmax, ymax = geo_bounds(geo_source)

        currentx = pos[0]
        currenty = pos[1]

        def translate_recursion(geom):
            if type(geom) == list:
                geoms = []
                for local_geom in geom:
                    res_geo = translate_recursion(local_geom)
                    try:
                        geoms += res_geo
                    except TypeError:
                        geoms.append(res_geo)
                return geoms
            else:
                return translate(geom, xoff=currentx, yoff=currenty)

        for row in range(rows):
            currentx = pos[0]

            for col in range(columns):
                trans_geo += translate_recursion(geo_source)
                if array_2d_type == 's':  # 'spacing'
                    currentx += (xmax - xmin + spacing_columns)
                else:   # 'offset'
                    currentx = pos[0] + off_x * (col + 1)    # because 'col' starts from 0 we increment by 1

            if array_2d_type == 's':  # 'spacing'
                currenty += (ymax - ymin + spacing_rows)
            else:   # 'offset;
                currenty = pos[1] + off_y * (row + 1)    # because 'row' starts from 0 we increment by 1

        return DrawToolUtilityShape(trans_geo)

    def circular_geo(self, pos):
        if pos[0] is None and pos[1] is None:
            cdx = self.draw_app.x
            cdy = self.draw_app.y
        else:
            cdx = pos[0] + self.origin[0]
            cdy = pos[1] + self.origin[1]

        utility_list = []

        try:
            radius = distance((cdx, cdy), self.origin)
        except Exception:
            radius = 0

        if radius == 0:
            self.draw_app.delete_utility_geometry()

        if len(self.points) >= 1 and radius > 0:
            try:
                if cdx < self.origin[0]:
                    radius = -radius

                # draw the temp geometry
                initial_angle = math.asin((cdy - self.origin[1]) / radius)
                temp_circular_geo = self.circular_util_shape(radius, initial_angle)

                temp_points = [
                    (self.origin[0], self.origin[1]),
                    (self.origin[0] + pos[0], self.origin[1] + pos[1])
                ]
                temp_line = LineString(temp_points)

                for geo_shape in temp_circular_geo:
                    utility_list.append(geo_shape.geo)
                utility_list.append(temp_line)

                return DrawToolUtilityShape(utility_list)
            except Exception as e:
                log.error("DrillArray.utility_geometry -- circular -> %s" % str(e))

    def circular_util_shape(self, radius, ini_angle):
        direction = self.ui.array_dir_radio.get_value()      # CW or CCW
        angle = self.ui.angle_entry.get_value()
        array_size = int(self.ui.array_size_entry.get_value())

        circular_geo = []
        for i in range(array_size):
            angle_radians = math.radians(angle * i)
            if direction == 'CW':
                x = radius * math.cos(-angle_radians + ini_angle)
                y = radius * math.sin(-angle_radians + ini_angle)
            else:
                x = radius * math.cos(angle_radians + ini_angle)
                y = radius * math.sin(angle_radians + ini_angle)

            for sshp in self.draw_app.get_selected():
                geo_sol = translate(sshp.geo, x, y)
                # geo_sol = affinity.rotate(geo_sol, angle=(math.pi - angle_radians), use_radians=True)

                circular_geo.append(DrawToolShape(geo_sol))

        return circular_geo

    def draw_cursor_data(self, pos=None, delete=False):
        if self.cursor_data_control is False:
            self.draw_app.app.plotcanvas.text_cursor.text = ""
            return

        if pos is None:
            pos = self.draw_app.snap_x, self.draw_app.snap_y

        if delete:
            if self.draw_app.app.use_3d_engine:
                self.draw_app.app.plotcanvas.text_cursor.parent = None
                self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None
            return

        # font size
        qsettings = QtCore.QSettings("Open Source", "FlatCAM_EVO")
        if qsettings.contains("hud_font_size"):
            fsize = qsettings.value('hud_font_size', type=int)
        else:
            fsize = 8

        ref_val = (0, 0) if self.origin is None else self.origin
        x = pos[0]
        y = pos[1]
        try:
            length = abs(np.sqrt((pos[0] - ref_val[0]) ** 2 + (pos[1] - ref_val[1]) ** 2))
        except IndexError:
            length = self.draw_app.app.dec_format(0.0, self.draw_app.app.decimals)
        units = self.draw_app.app.app_units.lower()

        x_dec = str(self.draw_app.app.dec_format(x, self.draw_app.app.decimals)) if x else '0.0'
        y_dec = str(self.draw_app.app.dec_format(y, self.draw_app.app.decimals)) if y else '0.0'
        length_dec = str(self.draw_app.app.dec_format(length, self.draw_app.app.decimals)) if length else '0.0'

        l1_txt = 'X:   %s [%s]' % (x_dec, units)
        l2_txt = 'Y:   %s [%s]' % (y_dec, units)
        l3_txt = 'L:   %s [%s]' % (length_dec, units)
        cursor_text = '%s\n%s\n\n%s' % (l1_txt, l2_txt, l3_txt)

        if self.draw_app.app.use_3d_engine:
            new_pos = self.draw_app.app.plotcanvas.translate_coords_2((x, y))
            x, y, __, ___ = self.draw_app.app.plotcanvas.translate_coords((new_pos[0] + 30, new_pos[1]))

            # text
            self.draw_app.app.plotcanvas.text_cursor.font_size = fsize
            self.draw_app.app.plotcanvas.text_cursor.text = cursor_text
            self.draw_app.app.plotcanvas.text_cursor.pos = x, y
            self.draw_app.app.plotcanvas.text_cursor.anchors = 'left', 'top'

            if self.draw_app.app.plotcanvas.text_cursor.parent is None:
                self.draw_app.app.plotcanvas.text_cursor.parent = self.draw_app.app.plotcanvas.view.scene

    def on_key(self, key):
        if key == 'C' or key == QtCore.Qt.Key.Key_C:
            self.cursor_data_control = not self.cursor_data_control

        # Jump to coords
        if key == QtCore.Qt.Key.Key_J or key == 'J':
            self.draw_app.app.on_jump_to()

        if key in [str(i) for i in range(10)] + ['.', ',', '+', '-', '/', '*'] or \
                key in [QtCore.Qt.Key.Key_0, QtCore.Qt.Key.Key_0, QtCore.Qt.Key.Key_1, QtCore.Qt.Key.Key_2,
                        QtCore.Qt.Key.Key_3, QtCore.Qt.Key.Key_4, QtCore.Qt.Key.Key_5, QtCore.Qt.Key.Key_6,
                        QtCore.Qt.Key.Key_7, QtCore.Qt.Key.Key_8, QtCore.Qt.Key.Key_9, QtCore.Qt.Key.Key_Minus,
                        QtCore.Qt.Key.Key_Plus, QtCore.Qt.Key.Key_Comma, QtCore.Qt.Key.Key_Period,
                        QtCore.Qt.Key.Key_Slash, QtCore.Qt.Key.Key_Asterisk]:
            try:
                # VisPy keys
                if self.copy_tool.length == 0:
                    self.copy_tool.length = str(key.name)
                else:
                    self.copy_tool.length = str(self.copy_tool.length) + str(key.name)
            except AttributeError:
                # Qt keys
                if self.copy_tool.length == 0:
                    self.copy_tool.length = chr(key)
                else:
                    self.copy_tool.length = str(self.copy_tool.length) + chr(key)

        if key == 'Enter' or key == QtCore.Qt.Key.Key_Return or key == QtCore.Qt.Key.Key_Enter:
            if self.copy_tool.length != 0:
                target_length = self.copy_tool.length
                if target_length is None:
                    self.copy_tool.length = 0.0
                    return _("Failed.")

                first_pt = self.points[-1]
                last_pt = self.draw_app.app.mouse

                seg_length = math.sqrt((last_pt[0] - first_pt[0]) ** 2 + (last_pt[1] - first_pt[1]) ** 2)
                if seg_length == 0.0:
                    return
                try:
                    new_x = first_pt[0] + (last_pt[0] - first_pt[0]) / seg_length * target_length
                    new_y = first_pt[1] + (last_pt[1] - first_pt[1]) / seg_length * target_length
                except ZeroDivisionError as err:
                    self.points = []
                    self.clean_up()
                    return '[ERROR_NOTCL] %s %s' % (_("Failed."), str(err).capitalize())

                if self.points[-1] != (new_x, new_y):
                    self.points.append((new_x, new_y))
                    self.draw_app.app.on_jump_to(custom_location=(new_x, new_y), fit_center=False)
                    self.destination = (new_x, new_y)
                    self.make()
                    self.draw_app.on_shape_complete()
                    self.draw_app.select_tool("select")
                    return "Done."

    def clean_up(self):
        self.draw_app.selected.clear()
        self.draw_app.ui.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        if self.draw_app.app.use_3d_engine:
            self.draw_app.app.plotcanvas.text_cursor.parent = None
            self.draw_app.app.plotcanvas.view.camera.zoom_callback = lambda *args: None

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass
        self.copy_tool.on_tab_close()


class AppExcEditor(QtCore.QObject):

    draw_shape_idx = -1

    def __init__(self, app):
        # assert isinstance(app, FlatCAMApp.App), "Expected the app to be a FlatCAMApp.App, got %s" % type(app)

        super(AppExcEditor, self).__init__()

        self.app = app
        self.canvas = self.app.plotcanvas
        self.units = self.app.app_units.upper()

        self.dec_format = self.app.dec_format

        # Number of decimals used by tools in this class
        self.decimals = self.app.decimals

        self.ui = AppExcEditorUI(app=self.app)

        self.edited_obj = None

        # ## Toolbar events and properties
        self.tools_exc = {}

        # ## Data
        self.active_tool = None
        self.in_action = False

        self.storage_dict = {}
        self.current_storage = []

        # build the data from the Excellon point into a dictionary
        #  {tool_dia: [geometry_in_points]}
        self.points_edit = {}
        self.slot_points_edit = {}

        self.sorted_diameters = []

        # here store the tools dict for the new excellon object
        self.new_tools = {}

        # dictionary to store the tool_row and diameters in plugin_table
        # it will be updated everytime self.build_ui() is called
        self.olddia_newdia = {}

        self.tool2tooldia = {}

        # this will store the value for the last selected tool, for use after clicking on canvas when the selection
        # is cleared but as a side effect also the selected tool is cleared
        self.last_tool_selected = None
        self.utility = []

        # this will flag if the Editor "tools" are launched from key shortcuts (True) or from menu toolbar (False)
        self.launched_from_shortcuts = False

        # this var will store the state of the toolbar before starting the editor
        self.toolbar_old_state = False

        if self.units == 'MM':
            self.tolerance = float(self.app.options["global_tolerance"])
        else:
            self.tolerance = float(self.app.options["global_tolerance"]) / 20

        # VisPy Visuals
        if self.app.use_3d_engine:
            self.shapes = self.canvas.new_shape_collection(layers=1)
            if self.canvas.big_cursor is True:
                self.tool_shape = self.canvas.new_shape_collection(layers=1, line_width=2)
            else:
                self.tool_shape = self.canvas.new_shape_collection(layers=1)
        else:
            from appGUI.PlotCanvasLegacy import ShapeCollectionLegacy
            self.shapes = ShapeCollectionLegacy(obj=self, app=self.app, name='shapes_exc_editor')
            self.tool_shape = ShapeCollectionLegacy(obj=self, app=self.app, name='tool_shapes_exc_editor')

        self.app.pool_recreated.connect(self.pool_recreated)

        # Remove from scene
        self.shapes.enabled = False
        self.tool_shape.enabled = False

        # ## List of selected shapes.
        self.selected = []

        self.move_timer = QtCore.QTimer()
        self.move_timer.setSingleShot(True)

        self.key = None  # Currently pressed key
        self.modifiers = None
        self.x = None  # Current mouse cursor clicked_pos
        self.y = None
        # Current snapped mouse clicked_pos
        self.snap_x = None
        self.snap_y = None
        self.clicked_pos = None

        # #############################################################################################################
        # Plugin Attributes
        # #############################################################################################################
        self.last_length = 0.0

        self.last_darray_type = None
        self.last_darray_size = None
        self.last_darray_lin_dir = None
        self.last_darray_circ_dir = None
        self.last_darray_pitch = None
        self.last_darray_lin_angle = None
        self.last_darray_circ_angle = None
        self.last_darray_radius = None

        self.last_sarray_radius = None
        self.last_sarray_circ_angle = None
        self.last_sarray_lin_angle = None
        self.last_sarray_pitch = None
        self.last_sarray_circ_dir = None
        self.last_sarray_lin_dir = None
        self.last_sarray_size = None
        self.last_sarray_type = None

        self.last_slot_length = None
        self.last_slot_direction = None
        self.last_slot_angle = None

        self.complete = False

        self.editor_options = {
            "global_gridx":     0.1,
            "global_gridy":     0.1,
            "snap_max":         0.05,
            "grid_snap":        True,
            "corner_snap":      False,
            "grid_gap_link":    True
        }
        self.editor_options.update(self.app.options)

        for option in self.editor_options:
            if option in self.app.options:
                self.editor_options[option] = self.app.options[option]

        self.data_defaults = {}

        self.rtree_exc_index = rtindex.Index()
        # flag to show if the object was modified
        self.is_modified = False

        self.edited_obj_name = ""

        # variable to store the total amount of drills per job
        self.tot_drill_cnt = 0
        self.tool_row = 0

        # variable to store the total amount of slots per job
        self.tot_slot_cnt = 0
        self.tool_row_slots = 0

        self.tool_row = 0

        # def entry2option(option, entry):
        #     self.editor_options[option] = float(entry.text())

        # Event signals disconnect id holders
        self.mp = None
        self.mm = None
        self.mr = None

        # #############################################################################################################
        # ######################### Excellon Editor Signals ###########################################################
        # #############################################################################################################

        self.ui.level.toggled.connect(self.on_level_changed)

        # connect the toolbar signals
        self.connect_exc_toolbar_signals()

        self.ui.convert_slots_btn.clicked.connect(self.on_slots_conversion)
        self.app.ui.delete_drill_btn.triggered.connect(self.on_delete_btn)
        self.ui.name_entry.returnPressed.connect(self.on_name_activate)
        self.ui.addtool_btn.clicked.connect(self.on_tool_add)
        self.ui.addtool_entry.editingFinished.connect(self.on_tool_add)
        self.ui.deltool_btn.clicked.connect(self.on_tool_delete)
        # self.ui.tools_table_exc.selectionModel().currentChanged.connect(self.on_row_selected)
        self.ui.tools_table_exc.cellPressed.connect(self.on_row_selected)
        self.ui.tools_table_exc.selectionModel().selectionChanged.connect(self.on_table_selection)  # noqa

        self.app.ui.exc_add_array_drill_menuitem.triggered.connect(self.exc_add_drill_array)
        self.app.ui.exc_add_drill_menuitem.triggered.connect(self.exc_add_drill)

        self.app.ui.exc_add_array_slot_menuitem.triggered.connect(self.exc_add_slot_array)
        self.app.ui.exc_add_slot_menuitem.triggered.connect(self.exc_add_slot)

        self.app.ui.exc_resize_drill_menuitem.triggered.connect(self.exc_resize_drills)
        self.app.ui.exc_copy_drill_menuitem.triggered.connect(self.exc_copy_drills)
        self.app.ui.exc_delete_drill_menuitem.triggered.connect(self.on_delete_btn)

        self.app.ui.exc_move_drill_menuitem.triggered.connect(self.exc_move_drills)
        self.ui.exit_editor_button.clicked.connect(lambda: self.app.on_editing_finished())

        # #############################################################################################################
        # ############################### TOOLS TABLE context menu ####################################################
        # #############################################################################################################
        self.ui.tools_table_exc.setupContextMenu()
        # self.ui.tools_table_exc.addContextMenu(
        #     _("Add"), self.on_aperture_add,
        #     icon=QtGui.QIcon(self.app.resource_location + "/plus16.png"))
        self.ui.tools_table_exc.addContextMenu(
            _("Delete"), lambda: self.on_tool_delete(),
            icon=QtGui.QIcon(self.app.resource_location + "/trash16.png"))

        self.app.log.debug("Initialization of the Excellon Editor is finished ...")

    def make_callback(self, thetool):
        def f():
            self.on_tool_select(thetool)

        return f

    def connect_exc_toolbar_signals(self) -> None:
        self.tools_exc.update({
            "drill_select":     {"button": self.app.ui.select_drill_btn,    "constructor": SelectEditorExc},
            "drill_add":        {"button": self.app.ui.add_drill_btn,       "constructor": DrillAdd},
            "drill_array":      {"button": self.app.ui.add_drill_array_btn, "constructor": DrillArray},
            "slot_add":         {"button": self.app.ui.add_slot_btn,        "constructor": SlotAdd},
            "slot_array":       {"button": self.app.ui.add_slot_array_btn,  "constructor": SlotArray},
            "drill_resize":     {"button": self.app.ui.resize_drill_btn,    "constructor": ResizeEditorExc},
            "drill_copy":       {"button": self.app.ui.copy_drill_btn,      "constructor": CopyEditorExc},
            "drill_move":       {"button": self.app.ui.move_drill_btn,      "constructor": MoveEditorExc},
        })

        for tool in self.tools_exc:
            self.tools_exc[tool]["button"].triggered.connect(self.make_callback(tool))  # Events
            self.tools_exc[tool]["button"].setCheckable(True)  # Checkable

    def pool_recreated(self, pool):
        self.shapes.pool = pool
        self.tool_shape.pool = pool

    @staticmethod
    def make_storage():
        # ## Shape storage.
        storage = AppRTreeStorage()
        storage.get_points = DrawToolShape.get_pts

        return storage

    def set_editor_ui(self):
        # updated units
        self.units = self.app.app_units.upper()

        self.olddia_newdia.clear()
        self.tool2tooldia.clear()

        # update the olddia_newdia dict to make sure we have an updated state of the plugin_table
        for key in self.points_edit:
            self.olddia_newdia[key] = key

        for key in self.slot_points_edit:
            if key not in self.olddia_newdia:
                self.olddia_newdia[key] = key

        sort_temp = []
        for diam in self.olddia_newdia:
            sort_temp.append(float(diam))
        self.sorted_diameters = sorted(sort_temp)

        # populate self.intial_table_rows dict with the tool number as keys and tool diameters as values
        if self.edited_obj.diameterless is False:
            for i in range(len(self.sorted_diameters)):
                tt_dia = self.sorted_diameters[i]
                self.tool2tooldia[i + 1] = tt_dia
        else:
            # the Excellon object has diameters that are bogus information, added by the application because the
            # Excellon file has no tool diameter information. In this case do not order the diameter in the table
            # but use the real order found in the edited_obj.tools
            for k, v in self.edited_obj.tools.items():
                tool_dia = float('%.*f' % (self.decimals, v['tooldia']))
                self.tool2tooldia[int(k)] = tool_dia

        # Init appGUI
        self.ui.addtool_entry.set_value(float(self.app.options['excellon_editor_newdia']))

        self.last_darray_type = 'linear'
        self.last_darray_size = int(self.app.options['excellon_editor_array_size'])
        self.last_darray_lin_dir = self.app.options['excellon_editor_lin_dir']
        self.last_darray_circ_dir = self.app.options['excellon_editor_circ_dir']
        self.last_darray_pitch = float(self.app.options['excellon_editor_lin_pitch'])
        self.last_darray_lin_angle = float(self.app.options['excellon_editor_lin_angle'])
        self.last_darray_circ_angle = float(self.app.options['excellon_editor_circ_angle'])
        self.last_darray_radius = 0.0

        self.last_slot_length = self.app.options['excellon_editor_slot_length']
        self.last_slot_direction = self.app.options['excellon_editor_slot_direction']
        self.last_slot_angle = self.app.options['excellon_editor_slot_angle']

        self.last_sarray_type = 'linear'
        self.last_sarray_size = int(self.app.options['excellon_editor_slot_array_size'])
        self.last_sarray_lin_dir = self.app.options['excellon_editor_slot_lin_dir']
        self.last_sarray_circ_dir = self.app.options['excellon_editor_slot_circ_dir']
        self.last_sarray_pitch = float(self.app.options['excellon_editor_slot_lin_pitch'])
        self.last_sarray_lin_angle = float(self.app.options['excellon_editor_slot_lin_angle'])
        self.last_sarray_circ_angle = float(self.app.options['excellon_editor_slot_circ_angle'])
        self.last_sarray_radius = 0.0

        # Show/Hide Advanced Options
        app_mode = self.app.options["global_app_level"]
        self.change_level(app_mode)

    def build_ui(self, first_run=None):

        try:
            # if connected, disconnect the signal from the slot on item_changed as it creates issues
            self.ui.tools_table_exc.itemChanged.disconnect()
        except (TypeError, AttributeError):
            pass

        try:
            self.ui.tools_table_exc.cellPressed.disconnect()
        except (TypeError, AttributeError):
            pass

        # updated units
        self.units = self.app.app_units.upper()

        # make a new name for the new Excellon object (the one with edited content)
        self.edited_obj_name = self.edited_obj.obj_options['name']
        self.ui.name_entry.set_value(self.edited_obj_name)

        sort_temp = []

        for diam in self.olddia_newdia:
            sort_temp.append(float(diam))
        self.sorted_diameters = sorted(sort_temp)

        # here, self.sorted_diameters will hold in a oblique way, the number of tools
        n = len(self.sorted_diameters)
        # we have (n+2) rows because there are 'n' tools, each a row, plus the last 2 rows for totals.
        self.ui.tools_table_exc.setRowCount(n + 2)

        self.tot_drill_cnt = 0
        self.tot_slot_cnt = 0

        self.tool_row = 0
        # this variable will serve as the real tool_number
        tool_id = 0

        for tool_no in self.sorted_diameters:
            tool_id += 1
            drill_cnt = 0  # variable to store the nr of drills per tool
            slot_cnt = 0  # variable to store the nr of slots per tool

            # Find no of drills for the current tool
            for tool_dia in self.points_edit:
                if float(tool_dia) == tool_no:
                    drill_cnt = len(self.points_edit[tool_dia])

            self.tot_drill_cnt += drill_cnt

            # try:
            #     # Find no of slots for the current tool
            #     for slot in self.slot_points_edit:
            #         if float(slot) == tool_no:
            #             slot_cnt += 1
            #
            #     self.tot_slot_cnt += slot_cnt
            # except AttributeError:
            #     # self.app.log.debug("No slots in the Excellon file")
            #     # Find no of slots for the current tool
            #     for tool_dia in self.slot_points_edit:
            #         if float(tool_dia) == tool_no:
            #             slot_cnt = len(self.slot_points_edit[tool_dia])
            #
            #     self.tot_slot_cnt += slot_cnt

            for tool_dia in self.slot_points_edit:
                if float(tool_dia) == tool_no:
                    slot_cnt = len(self.slot_points_edit[tool_dia])

            self.tot_slot_cnt += slot_cnt

            idd = QtWidgets.QTableWidgetItem('%d' % int(tool_id))
            idd.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tools_table_exc.setItem(self.tool_row, 0, idd)  # Tool name/id

            # Make sure that the drill diameter when in MM is with no more than 2 decimals
            # There are no drill bits in MM with more than 2 decimals diameter
            # For INCH the decimals should be no more than 4. There are no drills under 10mils
            dia = QtWidgets.QTableWidgetItem('%.*f' % (self.decimals, self.olddia_newdia[tool_no]))

            dia.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)

            drill_count = QtWidgets.QTableWidgetItem('%d' % drill_cnt)
            drill_count.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)

            # if the slot number is zero is better to not clutter the GUI with zero's so we print a space
            if slot_cnt > 0:
                slot_count = QtWidgets.QTableWidgetItem('%d' % slot_cnt)
            else:
                slot_count = QtWidgets.QTableWidgetItem('')
            slot_count.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)

            self.ui.tools_table_exc.setItem(self.tool_row, 1, dia)  # Diameter
            self.ui.tools_table_exc.setItem(self.tool_row, 2, drill_count)  # Number of drills per tool
            self.ui.tools_table_exc.setItem(self.tool_row, 3, slot_count)  # Number of drills per tool

            if first_run is True:
                # set now the last tool selected
                self.last_tool_selected = int(tool_id)

            self.tool_row += 1

        # make the diameter column editable
        for row in range(self.tool_row):
            self.ui.tools_table_exc.item(row, 1).setFlags(
                QtCore.Qt.ItemFlag.ItemIsEditable |
                QtCore.Qt.ItemFlag.ItemIsSelectable |
                QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tools_table_exc.item(row, 2).setForeground(QtGui.QColor(0, 0, 0))
            self.ui.tools_table_exc.item(row, 3).setForeground(QtGui.QColor(0, 0, 0))

        # add a last row with the Total number of drills
        # HACK: made the text on this cell '9999' such it will always be the one before last when sorting
        # it will have to have the foreground color (font color) white
        empty = QtWidgets.QTableWidgetItem('9998')
        empty.setForeground(QtGui.QColor(255, 255, 255))

        empty.setFlags(empty.flags() ^ QtCore.Qt.ItemFlag.ItemIsEnabled)
        empty_b = QtWidgets.QTableWidgetItem('')
        empty_b.setFlags(empty_b.flags() ^ QtCore.Qt.ItemFlag.ItemIsEnabled)

        label_tot_drill_count = QtWidgets.QTableWidgetItem(_('Total Drills'))
        tot_drill_count = QtWidgets.QTableWidgetItem('%d' % self.tot_drill_cnt)

        label_tot_drill_count.setFlags(label_tot_drill_count.flags() ^ QtCore.Qt.ItemFlag.ItemIsEnabled)
        tot_drill_count.setFlags(tot_drill_count.flags() ^ QtCore.Qt.ItemFlag.ItemIsEnabled)

        self.ui.tools_table_exc.setItem(self.tool_row, 0, empty)
        self.ui.tools_table_exc.setItem(self.tool_row, 1, label_tot_drill_count)
        self.ui.tools_table_exc.setItem(self.tool_row, 2, tot_drill_count)  # Total number of drills
        self.ui.tools_table_exc.setItem(self.tool_row, 3, empty_b)

        font = QtGui.QFont()
        font.setBold(True)
        # font.setWeight(75)

        for k in [1, 2]:
            self.ui.tools_table_exc.item(self.tool_row, k).setForeground(QtGui.QColor(127, 0, 255))
            self.ui.tools_table_exc.item(self.tool_row, k).setFont(font)

        self.tool_row += 1

        # add a last row with the Total number of slots
        # HACK: made the text on this cell '9999' such it will always be the last when sorting
        # it will have to have the foreground color (font color) white
        empty_2 = QtWidgets.QTableWidgetItem('9999')
        empty_2.setForeground(QtGui.QColor(255, 255, 255))

        empty_2.setFlags(empty_2.flags() ^ QtCore.Qt.ItemFlag.ItemIsEnabled)

        empty_3 = QtWidgets.QTableWidgetItem('')
        empty_3.setFlags(empty_3.flags() ^ QtCore.Qt.ItemFlag.ItemIsEnabled)

        label_tot_slot_count = QtWidgets.QTableWidgetItem(_('Total Slots'))
        tot_slot_count = QtWidgets.QTableWidgetItem('%d' % self.tot_slot_cnt)
        label_tot_slot_count.setFlags(label_tot_slot_count.flags() ^ QtCore.Qt.ItemFlag.ItemIsEnabled)
        tot_slot_count.setFlags(tot_slot_count.flags() ^ QtCore.Qt.ItemFlag.ItemIsEnabled)

        self.ui.tools_table_exc.setItem(self.tool_row, 0, empty_2)
        self.ui.tools_table_exc.setItem(self.tool_row, 1, label_tot_slot_count)
        self.ui.tools_table_exc.setItem(self.tool_row, 2, empty_3)
        self.ui.tools_table_exc.setItem(self.tool_row, 3, tot_slot_count)  # Total number of slots

        for kl in [1, 2, 3]:
            self.ui.tools_table_exc.item(self.tool_row, kl).setFont(font)
            self.ui.tools_table_exc.item(self.tool_row, kl).setForeground(QtGui.QColor(0, 70, 255))

        # all the tools are selected by default
        self.ui.tools_table_exc.selectColumn(0)
        #
        self.ui.tools_table_exc.resizeColumnsToContents()
        self.ui.tools_table_exc.resizeRowsToContents()

        vertical_header = self.ui.tools_table_exc.verticalHeader()
        # vertical_header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        vertical_header.hide()
        self.ui.tools_table_exc.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        horizontal_header = self.ui.tools_table_exc.horizontalHeader()
        horizontal_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        horizontal_header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        horizontal_header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        horizontal_header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        # horizontal_header.setStretchLastSection(True)

        # self.ui.tools_table_exc.setSortingEnabled(True)
        # sort by tool diameter
        self.ui.tools_table_exc.sortItems(1)

        # After sorting, to display also the number of drills in the right row we need to update self.initial_rows dict
        # with the new order. Of course the last 2 rows in the tool table are just for display therefore we don't
        # use them
        self.tool2tooldia.clear()
        for row in range(self.ui.tools_table_exc.rowCount() - 2):
            tool = int(self.ui.tools_table_exc.item(row, 0).text())
            diameter = float(self.ui.tools_table_exc.item(row, 1).text())
            self.tool2tooldia[tool] = diameter

        self.ui.tools_table_exc.setMinimumHeight(self.ui.tools_table_exc.getHeight())
        self.ui.tools_table_exc.setMaximumHeight(self.ui.tools_table_exc.getHeight())

        # make sure no rows are selected so the user have to click the correct row, meaning selecting the correct tool
        self.ui.tools_table_exc.clearSelection()

        # Remove anything else in the GUI Properties Tab
        self.app.ui.properties_scroll_area.takeWidget()
        # Put ourselves in the GUI Properties Tab
        self.app.ui.properties_scroll_area.setWidget(self.ui.exc_edit_widget)
        # Switch notebook to Properties page
        self.app.ui.notebook.setCurrentWidget(self.app.ui.properties_tab)

        # we reactivate the signals after the after the tool adding as we don't need to see the tool been populated
        self.ui.tools_table_exc.itemChanged.connect(self.on_tool_edit)
        self.ui.tools_table_exc.cellPressed.connect(self.on_row_selected)

    def change_level(self, level):
        """

        :param level:   application level: either 'b' or 'a'
        :type level:    str
        :return:
        """

        if level == 'a':
            self.ui.level.setChecked(True)
        else:
            self.ui.level.setChecked(False)
        self.on_level_changed(self.ui.level.isChecked())

    def on_level_changed(self, checked):
        if not checked:
            self.ui.level.setText('%s' % _('Beginner'))
            self.ui.level.setStyleSheet("""
                                        QToolButton
                                        {
                                            color: green;
                                        }
                                        """)

            # Context Menu section
            # self.ui.tools_table_exc.removeContextMenu()
        else:
            self.ui.level.setText('%s' % _('Advanced'))
            self.ui.level.setStyleSheet("""
                                        QToolButton
                                        {
                                            color: red;
                                        }
                                        """)

            # Context Menu section
            # self.ui.tools_table_exc.setupContextMenu()

    def on_tool_add(self, tooldia=None):
        self.is_modified = True
        if tooldia:
            tool_dia = tooldia
        else:
            try:
                tool_dia = float(self.ui.addtool_entry.get_value())
            except ValueError:
                # try to convert comma to decimal point. if it's still not working error message and return
                try:
                    tool_dia = float(self.ui.addtool_entry.get_value().replace(',', '.'))
                except ValueError:
                    self.app.inform.emit('[ERROR_NOTCL] %s' % _("Wrong value format entered, use a number."))
                    return

        if tool_dia not in self.olddia_newdia:
            storage_elem = AppGeoEditor.make_storage()
            self.storage_dict[tool_dia] = storage_elem

            # self.olddia_newdia dict keeps the evidence on current tools diameters as keys and gets updated on values
            # each time a tool diameter is edited or added
            self.olddia_newdia[tool_dia] = tool_dia
        else:
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Tool already in the original or actual tool list.\n" 
                                                          "Save and reedit Excellon if you need to add this tool. "))
            return

        # since we add a new tool, we update also the initial state of the plugin_table through it's dictionary
        # we add a new entry in the tool2tooldia dict
        self.tool2tooldia[len(self.olddia_newdia)] = tool_dia

        self.app.inform.emit('[success] %s: %s %s' % (_("Added new tool with dia"), str(tool_dia), str(self.units)))

        self.build_ui()

        # make a quick sort through the tool2tooldia dict so we find which row to select
        row_to_be_selected = None
        for key in sorted(self.tool2tooldia):
            if self.tool2tooldia[key] == tool_dia:
                row_to_be_selected = int(key) - 1
                self.last_tool_selected = int(key)
                break
        try:
            self.ui.tools_table_exc.selectRow(row_to_be_selected)
        except TypeError as e:
            self.app.log.debug("AppExcEditor.on_tool_add() --> %s" % str(e))

    def on_tool_delete(self, dia=None):
        self.is_modified = True
        deleted_tool_dia_list = []

        try:
            if dia is None or dia is False:
                # deleted_tool_dia = float(
                #     self.ui.tools_table_exc.item(self.ui.tools_table_exc.currentRow(), 1).text())
                for index in self.ui.tools_table_exc.selectionModel().selectedRows():
                    row = index.row()
                    deleted_tool_dia_list.append(float(self.ui.tools_table_exc.item(row, 1).text()))
            else:
                if isinstance(dia, list):
                    for dd in dia:
                        deleted_tool_dia_list.append(float('%.*f' % (self.decimals, dd)))
                else:
                    deleted_tool_dia_list.append(float('%.*f' % (self.decimals, dia)))
        except Exception:
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Select a tool in Tool Table"))
            return

        for deleted_tool_dia in deleted_tool_dia_list:

            # delete the storage used for that tool
            storage_elem = AppGeoEditor.make_storage()
            self.storage_dict[deleted_tool_dia] = storage_elem
            self.storage_dict.pop(deleted_tool_dia, None)

            # I've added this flag_del variable because dictionary don't like
            # having keys deleted while iterating through them
            flag_del = []
            # self.points_edit.pop(deleted_tool_dia, None)
            for deleted_tool in self.tool2tooldia:
                if self.tool2tooldia[deleted_tool] == deleted_tool_dia:
                    flag_del.append(deleted_tool)

            if flag_del:
                for tool_to_be_deleted in flag_del:
                    # delete the tool
                    self.tool2tooldia.pop(tool_to_be_deleted, None)

                    # delete also the drills from points_edit dict just in case we add the tool again,
                    # we don't want to show the number of drills from before was deleter
                    self.points_edit[deleted_tool_dia] = []

            self.olddia_newdia.pop(deleted_tool_dia, None)

            self.app.inform.emit('[success] %s: %s %s' %
                                 (_("Deleted tool with diameter"), str(deleted_tool_dia), str(self.units)))

        self.replot()
        # self.app.inform.emit("Could not delete selected tool")

        self.build_ui()

    def on_tool_edit(self, item_changed):
        # if connected, disconnect the signal from the slot on item_changed as it creates issues
        try:
            self.ui.tools_table_exc.itemChanged.disconnect()
        except TypeError:
            pass

        try:
            self.ui.tools_table_exc.cellPressed.disconnect()
        except TypeError:
            pass
        # self.ui.tools_table_exc.selectionModel().currentChanged.disconnect()

        self.is_modified = True
        # new_dia = None

        try:
            new_dia = float(self.ui.tools_table_exc.currentItem().text())
        except ValueError as e:
            self.app.log.debug("AppExcEditor.on_tool_edit() --> %s" % str(e))
            return

        row_of_item_changed = self.ui.tools_table_exc.currentRow()
        # rows start with 0, tools start with 1 so we adjust the value by 1
        key_in_tool2tooldia = row_of_item_changed + 1
        old_dia = self.tool2tooldia[key_in_tool2tooldia]

        # SOURCE storage
        source_storage = self.storage_dict[old_dia]

        # DESTINATION storage
        # tool diameter is not used so we create a new tool with the desired diameter
        if new_dia not in self.olddia_newdia:
            destination_storage = AppGeoEditor.make_storage()
            self.storage_dict[new_dia] = destination_storage

            # self.olddia_newdia dict keeps the evidence on current tools diameters as keys and gets updated on values
            # each time a tool diameter is edited or added
            self.olddia_newdia[new_dia] = new_dia
        else:
            # tool diameter is already in use so we move the drills from the prior tool to the new tool
            destination_storage = self.storage_dict[new_dia]

        # since we add a new tool, we update also the intial state of the plugin_table through it's dictionary
        # we add a new entry in the tool2tooldia dict
        self.tool2tooldia[len(self.olddia_newdia)] = new_dia

        # CHANGE the elements geometry according to the new diameter
        factor = new_dia / old_dia
        new_geo = Polygon()
        for shape_exc in source_storage.get_objects():
            geo_list = []
            if isinstance(shape_exc.geo, MultiLineString):
                for subgeo in shape_exc.geo.geoms:
                    geo_list.append(scale(subgeo, xfact=factor, yfact=factor, origin='center'))
                new_geo = MultiLineString(geo_list)
            elif isinstance(shape_exc.geo, Polygon):
                # I don't have any info regarding the angle of the slot geometry, nor how thick it is or
                # how long it is given the angle. So I will have to make an approximation because
                # we need to conserve the slot length, we only resize the diameter for the tool
                # Therefore scaling won't work and buffering will not work either.

                # First we get the Linestring that is one that the original slot is built around with the
                # tool having the diameter sel_dia
                poly = shape_exc.geo
                xmin, ymin, xmax, ymax = poly.bounds
                # a line that is certain to be bigger than our slot because it's the diagonal
                # of it's bounding box
                poly_diagonal = LineString([(xmin, ymin), (xmax, ymax)])
                poly_centroid = poly.centroid
                # center of the slot geometry
                poly_center = (poly_centroid.x, poly_centroid.y)

                # make a list of intersections with the rotated line
                list_of_cuttings = []
                for angle in range(0, 359, 1):
                    rot_poly_diagonal = rotate(poly_diagonal, angle=angle, origin=poly_center)
                    cut_line = rot_poly_diagonal.intersection(poly)
                    cut_line_len = cut_line.length
                    list_of_cuttings.append(
                        (cut_line_len, cut_line)
                    )
                # find the cut_line with the maximum length which is the LineString for which the start
                # and stop point are the start and stop point of the slot as in the Gerber file
                cut_line_with_max_length = max(list_of_cuttings, key=lambda i: i[0])[1]
                # find the coordinates of this line
                cut_line_with_max_length_coords = list(cut_line_with_max_length.coords)
                # extract the first and last point of the line and build some buffered polygon circles
                # around them
                start_pt = Point(cut_line_with_max_length_coords[0])
                stop_pt = Point(cut_line_with_max_length_coords[1])
                start_cut_geo = start_pt.buffer(new_dia / 2)
                stop_cut_geo = stop_pt.buffer(new_dia / 2)

                # and we cut the above circle polygons from our line and get in this way a line around
                # which we can build the new slot by buffering with the new tool diameter
                new_line = cut_line_with_max_length.difference(start_cut_geo)
                new_line = new_line.difference(stop_cut_geo)

                # create the geometry for the resized slot by buffering with half of the
                # new diameter value: new_dia
                new_geo = new_line.buffer(new_dia / 2)

            try:
                self.points_edit.pop(old_dia, None)
            except KeyError:
                pass
            try:
                self.slot_points_edit.pop(old_dia, None)
            except KeyError:
                pass

            # add bogus drill/slots points (for total count of drills/slots)
            # for drills
            if isinstance(shape_exc.geo, MultiLineString):
                if new_dia not in self.points_edit:
                    self.points_edit[new_dia] = [(0, 0)]
                else:
                    self.points_edit[new_dia].append((0, 0))

            # for slots
            if isinstance(shape_exc.geo, Polygon):
                if new_dia not in self.slot_points_edit:
                    self.slot_points_edit[new_dia] = [(0, 0)]
                else:
                    self.slot_points_edit[new_dia].append((0, 0))

            self.add_exc_shape(shp=DrawToolShape(new_geo), storage=destination_storage)

        # update the UI and the CANVAS
        self.build_ui()
        self.replot()

        # delete the old tool
        self.on_tool_delete(dia=old_dia)

        # we reactivate the signals after the after the tool editing
        self.ui.tools_table_exc.itemChanged.connect(self.on_tool_edit)
        self.ui.tools_table_exc.cellPressed.connect(self.on_row_selected)

        self.app.inform.emit('[success] %s' % _("Done."))

        # self.ui.tools_table_exc.selectionModel().currentChanged.connect(self.on_row_selected)

    def on_name_activate(self):
        self.edited_obj_name = self.ui.name_entry.get_value()

    def activate(self):
        # adjust the status of the menu entries related to the editor
        self.app.ui.menueditedit.setDisabled(True)
        self.app.ui.menueditok.setDisabled(False)
        # adjust the visibility of some of the canvas context menu
        self.app.ui.popmenu_edit.setVisible(False)
        self.app.ui.popmenu_save.setVisible(True)

        self.connect_canvas_event_handlers()

        # initialize working objects
        self.storage_dict = {}
        self.current_storage = []
        self.points_edit = {}
        self.sorted_diameters = []

        self.new_tools = {}

        self.olddia_newdia = {}

        self.shapes.enabled = True
        self.tool_shape.enabled = True
        # self.app.app_cursor.enabled = True

        self.app.ui.corner_snap_btn.setVisible(True)
        self.app.ui.snap_magnet.setVisible(True)

        self.app.ui.exc_editor_menu.setDisabled(False)
        self.app.ui.exc_editor_menu.menuAction().setVisible(True)

        self.app.ui.editor_exit_btn_ret_action.setVisible(True)
        self.app.ui.editor_start_btn.setVisible(False)
        self.app.ui.e_editor_cmenu.setEnabled(True)

        self.app.ui.exc_edit_toolbar.setDisabled(False)
        self.app.ui.exc_edit_toolbar.setVisible(True)
        # self.app.ui.grid_toolbar.setDisabled(False)

        # start with GRID toolbar activated
        if self.app.ui.grid_snap_btn.isChecked() is False:
            self.app.ui.grid_snap_btn.trigger()

        self.app.ui.popmenu_disable.setVisible(False)
        self.app.ui.cmenu_newmenu.menuAction().setVisible(False)
        self.app.ui.popmenu_properties.setVisible(False)
        self.app.ui.e_editor_cmenu.menuAction().setVisible(True)
        self.app.ui.g_editor_cmenu.menuAction().setVisible(False)
        self.app.ui.grb_editor_cmenu.menuAction().setVisible(False)

        self.app.ui.pop_menucolor.menuAction().setVisible(False)
        self.app.ui.popmenu_numeric_move.setVisible(False)
        self.app.ui.popmenu_move2origin.setVisible(False)

        # show the UI
        self.ui.drills_frame.show()

    def deactivate(self):
        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        # adjust the status of the menu entries related to the editor
        self.app.ui.menueditedit.setDisabled(False)
        self.app.ui.menueditok.setDisabled(True)
        # adjust the visibility of some of the canvas context menu
        self.app.ui.popmenu_edit.setVisible(True)
        self.app.ui.popmenu_save.setVisible(False)

        self.disconnect_canvas_event_handlers()
        self.clear()
        self.app.ui.exc_edit_toolbar.setDisabled(True)

        self.app.ui.corner_snap_btn.setVisible(False)
        self.app.ui.snap_magnet.setVisible(False)

        # set the Editor Toolbar visibility to what was before entering in the Editor
        self.app.ui.exc_edit_toolbar.setVisible(False) if self.toolbar_old_state is False \
            else self.app.ui.exc_edit_toolbar.setVisible(True)

        # Disable visuals
        self.shapes.enabled = False
        self.tool_shape.enabled = False
        # self.app.app_cursor.enabled = False

        self.app.ui.exc_editor_menu.setDisabled(True)
        self.app.ui.exc_editor_menu.menuAction().setVisible(False)

        self.app.ui.editor_exit_btn_ret_action.setVisible(False)
        self.app.ui.editor_start_btn.setVisible(True)

        self.app.ui.popmenu_disable.setVisible(True)
        self.app.ui.cmenu_newmenu.menuAction().setVisible(True)
        self.app.ui.popmenu_properties.setVisible(True)
        self.app.ui.g_editor_cmenu.menuAction().setVisible(False)
        self.app.ui.e_editor_cmenu.menuAction().setVisible(False)
        self.app.ui.grb_editor_cmenu.menuAction().setVisible(False)

        self.app.ui.pop_menucolor.menuAction().setVisible(True)
        self.app.ui.popmenu_numeric_move.setVisible(True)
        self.app.ui.popmenu_move2origin.setVisible(True)

        # Show original geometry
        if self.edited_obj:
            self.edited_obj.visible = True

        # hide the UI
        self.ui.drills_frame.hide()

    def connect_canvas_event_handlers(self):
        # ## Canvas events

        # first connect to new, then disconnect the old handlers
        # don't ask why but if there is nothing connected I've seen issues
        self.mp = self.canvas.graph_event_connect('mouse_press', self.on_canvas_click)
        self.mm = self.canvas.graph_event_connect('mouse_move', self.on_canvas_move)
        self.mr = self.canvas.graph_event_connect('mouse_release', self.on_exc_click_release)

        # make sure that the shortcuts key and mouse events will no longer be linked to the methods from FlatCAMApp
        # but those from AppGeoEditor
        if self.app.use_3d_engine:
            self.app.plotcanvas.graph_event_disconnect('mouse_press', self.app.on_mouse_click_over_plot)
            self.app.plotcanvas.graph_event_disconnect('mouse_move', self.app.on_mouse_move_over_plot)
            self.app.plotcanvas.graph_event_disconnect('mouse_release', self.app.on_mouse_click_release_over_plot)
            self.app.plotcanvas.graph_event_disconnect('mouse_double_click', self.app.on_mouse_double_click_over_plot)
        else:
            self.app.plotcanvas.graph_event_disconnect(self.app.mp)
            self.app.plotcanvas.graph_event_disconnect(self.app.mm)
            self.app.plotcanvas.graph_event_disconnect(self.app.mr)
            self.app.plotcanvas.graph_event_disconnect(self.app.mdc)

        self.app.collection.view.clicked.disconnect()

        self.app.ui.popmenu_copy.triggered.disconnect()
        self.app.ui.popmenu_delete.triggered.disconnect()
        self.app.ui.popmenu_move.triggered.disconnect()

        self.app.ui.popmenu_copy.triggered.connect(self.exc_copy_drills)
        self.app.ui.popmenu_delete.triggered.connect(self.on_delete_btn)
        self.app.ui.popmenu_move.triggered.connect(self.exc_move_drills)

        # Excellon Editor
        self.app.ui.drill.triggered.connect(self.exc_add_drill)
        self.app.ui.drill_array.triggered.connect(self.exc_add_drill_array)

    def disconnect_canvas_event_handlers(self):
        # we restore the key and mouse control to FlatCAMApp method
        # first connect to new, then disconnect the old handlers
        # don't ask why but if there is nothing connected I've seen issues
        self.app.mp = self.app.plotcanvas.graph_event_connect('mouse_press', self.app.on_mouse_click_over_plot)
        self.app.mm = self.app.plotcanvas.graph_event_connect('mouse_move', self.app.on_mouse_move_over_plot)
        self.app.mr = self.app.plotcanvas.graph_event_connect('mouse_release',
                                                              self.app.on_mouse_click_release_over_plot)
        self.app.mdc = self.app.plotcanvas.graph_event_connect('mouse_double_click',
                                                               self.app.on_mouse_double_click_over_plot)
        self.app.collection.view.clicked.connect(self.app.collection.on_mouse_down)

        if self.app.use_3d_engine:
            self.canvas.graph_event_disconnect('mouse_press', self.on_canvas_click)
            self.canvas.graph_event_disconnect('mouse_move', self.on_canvas_move)
            self.canvas.graph_event_disconnect('mouse_release', self.on_exc_click_release)
        else:
            self.canvas.graph_event_disconnect(self.mp)
            self.canvas.graph_event_disconnect(self.mm)
            self.canvas.graph_event_disconnect(self.mr)

        try:
            self.app.ui.popmenu_copy.triggered.disconnect(self.exc_copy_drills)
        except (TypeError, AttributeError):
            pass

        try:
            self.app.ui.popmenu_delete.triggered.disconnect(self.on_delete_btn)
        except (TypeError, AttributeError):
            pass

        try:
            self.app.ui.popmenu_move.triggered.disconnect(self.exc_move_drills)
        except (TypeError, AttributeError):
            pass

        self.app.ui.popmenu_copy.triggered.connect(self.app.on_copy_command)
        self.app.ui.popmenu_delete.triggered.connect(self.app.on_delete)
        self.app.ui.popmenu_move.triggered.connect(self.app.obj_move)

        # Excellon Editor
        try:
            self.app.ui.drill.triggered.disconnect(self.exc_add_drill)
        except (TypeError, AttributeError):
            pass

        try:
            self.app.ui.drill_array.triggered.disconnect(self.exc_add_drill_array)
        except (TypeError, AttributeError):
            pass

        try:
            self.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass

    def clear(self):
        self.active_tool = None
        # self.shape_buffer = []
        self.selected.clear()

        self.points_edit = {}
        self.new_tools = {}

        # self.storage_dict = {}

        self.shapes.clear(update=True)
        self.tool_shape.clear(update=True)

        # self.storage = AppExcEditor.make_storage()
        self.replot()

    def edit_fcexcellon(self, edited_obj):
        """
        Imports the geometry from the given FlatCAM Excellon object into the editor.

        :param edited_obj:  ExcellonObject object
        :return:            None
        """

        self.deactivate()
        self.activate()

        # create a reference to the edited object
        self.edited_obj = edited_obj

        # Hide original geometry
        edited_obj.visible = False

        if self.edited_obj:
            outname = self.edited_obj.obj_options['name']
        else:
            outname = ''

        self.data_defaults = {
            "name":                         outname + '_drill',
            "plot":                         self.app.options["excellon_plot"],
            "solid":                        self.app.options["excellon_solid"],
            "multicolored":                 self.app.options["excellon_multicolored"],
            "merge_fuse_tools":             self.app.options["excellon_merge_fuse_tools"],
            "format_upper_in":              self.app.options["excellon_format_upper_in"],
            "format_lower_in":              self.app.options["excellon_format_lower_in"],
            "format_upper_mm":              self.app.options["excellon_format_upper_mm"],
            "lower_mm":                     self.app.options["excellon_format_lower_mm"],
            "zeros":                        self.app.options["excellon_zeros"],

            "tools_drill_tool_order":       self.app.options["tools_drill_tool_order"],
            "tools_drill_cutz":             self.app.options["tools_drill_cutz"],
            "tools_drill_multidepth":       self.app.options["tools_drill_multidepth"],
            "tools_drill_depthperpass":     self.app.options["tools_drill_depthperpass"],
            "tools_drill_travelz":          self.app.options["tools_drill_travelz"],

            "tools_drill_feedrate_z":       self.app.options["tools_drill_feedrate_z"],
            "tools_drill_feedrate_rapid":   self.app.options["tools_drill_feedrate_rapid"],

            "tools_drill_toolchange":       self.app.options["tools_drill_toolchange"],
            "tools_drill_toolchangez":      self.app.options["tools_drill_toolchangez"],
            "tools_drill_toolchangexy":     self.app.options["tools_drill_toolchangexy"],

            # Drill Slots
            "tools_drill_drill_slots":      self.app.options["tools_drill_drill_slots"],
            "tools_drill_drill_overlap":    self.app.options["tools_drill_drill_overlap"],
            "tools_drill_last_drill":       self.app.options["tools_drill_last_drill"],

            "tools_drill_endz":             self.app.options["tools_drill_endz"],
            "tools_drill_endxy":            self.app.options["tools_drill_endxy"],
            "tools_drill_startz":           self.app.options["tools_drill_startz"],
            "tools_drill_offset":           self.app.options["tools_drill_offset"],
            "tools_drill_spindlespeed":     self.app.options["tools_drill_spindlespeed"],
            "tools_drill_dwell":            self.app.options["tools_drill_dwell"],
            "tools_drill_dwelltime":        self.app.options["tools_drill_dwelltime"],
            "tools_drill_ppname_e":         self.app.options["tools_drill_ppname_e"],
            "tools_drill_z_p_depth":         self.app.options["tools_drill_z_p_depth"],
            "tools_drill_feedrate_probe":   self.app.options["tools_drill_feedrate_probe"],
            "tools_drill_spindledir":       self.app.options["tools_drill_spindledir"],
            "tools_drill_f_plunge":         self.app.options["tools_drill_f_plunge"],
            "tools_drill_f_retract":        self.app.options["tools_drill_f_retract"],

            "tools_drill_area_exclusion":   self.app.options["tools_drill_area_exclusion"],
            "tools_drill_area_shape":       self.app.options["tools_drill_area_shape"],
            "tools_drill_area_strategy":    self.app.options["tools_drill_area_strategy"],
            "tools_drill_area_overz":       self.app.options["tools_drill_area_overz"],
        }

        # fill in self.default_data values from self.obj_options
        for opt_key, opt_val in self.app.options.items():
            if opt_key.find('excellon_') == 0:
                self.data_defaults[opt_key] = deepcopy(opt_val)

        self.points_edit = {}
        # build the self.points_edit dict {dimaters: [point_list]}
        for tool, tool_dict in self.edited_obj.tools.items():
            tool_dia = self.dec_format(self.edited_obj.tools[tool]['tooldia'])

            if 'drills' in tool_dict and tool_dict['drills']:
                for drill in tool_dict['drills']:
                    try:
                        self.points_edit[tool_dia].append(drill)
                    except KeyError:
                        self.points_edit[tool_dia] = [drill]

        self.slot_points_edit = {}
        # build the self.slot_points_edit dict {dimaters: {"start": Point, "stop": Point}}
        for tool, tool_dict in self.edited_obj.tools.items():
            tool_dia = float('%.*f' % (self.decimals, self.edited_obj.tools[tool]['tooldia']))

            if 'slots' in tool_dict and tool_dict['slots']:
                for slot in tool_dict['slots']:
                    try:
                        self.slot_points_edit[tool_dia].append({
                            "start": slot[0],
                            "stop": slot[1]
                        })
                    except KeyError:
                        self.slot_points_edit[tool_dia] = [{
                            "start": slot[0],
                            "stop": slot[1]
                        }]

        # Set selection tolerance
        # DrawToolShape.tolerance = fc_excellon.drawing_tolerance * 10

        self.select_tool("drill_select")

        # reset the tool table
        self.ui.tools_table_exc.clear()
        self.ui.tools_table_exc.setHorizontalHeaderLabels(['#', _('Diameter'), 'D', 'S'])
        self.last_tool_selected = None

        self.set_editor_ui()

        # now that we have data, create the appGUI interface and add it to the Tool Tab
        self.build_ui(first_run=True)

        # we activate this after the initial build as we don't need to see the tool been populated
        self.ui.tools_table_exc.itemChanged.connect(self.on_tool_edit)

        # build the geometry for each tool-diameter, each drill will be represented by a '+' symbol
        # and then add it to the storage elements (each storage elements is a member of a list
        for tool_dia in self.points_edit:
            storage_elem = AppGeoEditor.make_storage()
            for point in self.points_edit[tool_dia]:
                # make a '+' sign, the line length is the tool diameter
                start_hor_line = ((point.x - (tool_dia / 2)), point.y)
                stop_hor_line = ((point.x + (tool_dia / 2)), point.y)
                start_vert_line = (point.x, (point.y - (tool_dia / 2)))
                stop_vert_line = (point.x, (point.y + (tool_dia / 2)))
                shape_geo = MultiLineString([(start_hor_line, stop_hor_line), (start_vert_line, stop_vert_line)])
                if shape_geo is not None:
                    self.add_exc_shape(DrawToolShape(shape_geo), storage_elem)
            self.storage_dict[tool_dia] = storage_elem

        # slots
        for tool_dia in self.slot_points_edit:
            buf_value = float(tool_dia) / 2
            for elem_dict in self.slot_points_edit[tool_dia]:

                line_geo = LineString([elem_dict['start'], elem_dict['stop']])
                shape_geo = line_geo.buffer(buf_value)

                if tool_dia not in self.storage_dict:
                    storage_elem = AppGeoEditor.make_storage()
                    self.storage_dict[tool_dia] = storage_elem

                if shape_geo is not None:
                    self.add_exc_shape(DrawToolShape(shape_geo), self.storage_dict[tool_dia])

        self.replot()

        # add a first tool in the Tool Table but only if the Excellon Object is empty
        if not self.tool2tooldia:
            self.on_tool_add(self.dec_format(float(self.app.options['excellon_editor_newdia'])))

    def update_fcexcellon(self, exc_obj):
        """
        Create a new Excellon object that contain the edited content of the source Excellon object

        :param exc_obj: ExcellonObject
        :return: None
        """

        # this dictionary will contain tooldia's as keys and a list of coordinates tuple as values
        # the values of this dict are coordinates of the holes (drills)
        edited_points = {}

        """
         - this dictionary will contain tooldia's as keys and a list of another dicts as values
         - the dict element of the list has the structure
         ================  ====================================
        Key               Value
        ================  ====================================
        start             (Shapely.Point) Start point of the slot
        stop              (Shapely.Point) Stop point of the slot
        ================  ====================================
        """
        edited_slot_points = {}

        for storage_tooldia in self.storage_dict:
            for x in self.storage_dict[storage_tooldia].get_objects():
                if isinstance(x.geo, MultiLineString):
                    # all x.geo in self.storage_dict[storage] are MultiLinestring objects for drills
                    # each MultiLineString is made out of Linestrings
                    # select first Linestring object in the current MultiLineString
                    first_linestring = x.geo.geoms[0]
                    # get it's coordinates
                    first_linestring_coords = first_linestring.coords
                    x_coord = first_linestring_coords[0][0] + (float(first_linestring.length / 2))
                    y_coord = first_linestring_coords[0][1]

                    # create a tuple with the coordinates (x, y) and add it to the list that is the value of the
                    # edited_points dictionary
                    point = (x_coord, y_coord)
                    if storage_tooldia not in edited_points:
                        edited_points[storage_tooldia] = [point]
                    else:
                        edited_points[storage_tooldia].append(point)
                elif isinstance(x.geo, Polygon):
                    # create a tuple with the points (start, stop) and add it to the list that is the value of the
                    # edited_points dictionary

                    # first determine the start and stop coordinates for the slot knowing the geometry and the tool
                    # diameter
                    radius = float(storage_tooldia) / 2
                    radius = radius - 0.0000001

                    poly = x.geo
                    poly = poly.buffer(-radius)

                    if not poly.is_valid or poly.is_empty:
                        # print("Polygon not valid: %s" % str(poly.wkt))
                        continue

                    xmin, ymin, xmax, ymax = poly.bounds
                    line_one = LineString([(xmin, ymin), (xmax, ymax)]).intersection(poly).length
                    line_two = LineString([(xmin, ymax), (xmax, ymin)]).intersection(poly).length

                    if line_one < line_two:
                        point_elem = {
                            "start": (xmin, ymax),
                            "stop": (xmax, ymin)
                        }
                    else:
                        point_elem = {
                            "start": (xmin, ymin),
                            "stop": (xmax, ymax)
                        }

                    if storage_tooldia not in edited_slot_points:
                        edited_slot_points[storage_tooldia] = [point_elem]
                    else:
                        edited_slot_points[storage_tooldia].append(point_elem)

        # recreate the drills and tools to be added to the new Excellon edited object
        # first, we look in the tool table if one of the tool diameters was changed then
        # append that a tuple formed by (old_dia, edited_dia) to a list
        changed_key = set()
        for initial_dia in self.olddia_newdia:
            edited_dia = self.olddia_newdia[initial_dia]
            if edited_dia != initial_dia:
                # for drills
                for old_dia in edited_points:
                    if old_dia == initial_dia:
                        changed_key.add((old_dia, edited_dia))
                # for slots
                for old_dia in edited_slot_points:
                    if old_dia == initial_dia:
                        changed_key.add((old_dia, edited_dia))
            # if the initial_dia is not in edited_points it means it is a new tool with no drill points
            # (and we have to add it)
            # because in case we have drill points it will have to be already added in edited_points
            # if initial_dia not in edited_points.keys():
            #     edited_points[initial_dia] = []

        for el in changed_key:
            edited_points[el[1]] = edited_points.pop(el[0])
            edited_slot_points[el[1]] = edited_slot_points.pop(el[0])

        # Let's sort the edited_points dictionary by keys (diameters) and store the result in a zipped list
        # ordered_edited_points is a ordered list of tuples;
        # element[0] of the tuple is the diameter and
        # element[1] of the tuple is a list of coordinates (a tuple themselves)
        ordered_edited_points = sorted(zip(edited_points.keys(), edited_points.values()))

        current_tool = 0
        for tool_dia in ordered_edited_points:
            current_tool += 1

            # create the self.tools for the new Excellon object (the one with edited content)
            if current_tool not in self.new_tools:
                self.new_tools[current_tool] = {}
            self.new_tools[current_tool]['tooldia'] = float(tool_dia[0])

            # add in self.tools the 'solid_geometry' key, the value (a list) is populated below
            self.new_tools[current_tool]['solid_geometry'] = []

            # create the self.drills for the new Excellon object (the one with edited content)
            for point in tool_dia[1]:
                try:
                    self.new_tools[current_tool]['drills'].append(Point(point))
                except KeyError:
                    self.new_tools[current_tool]['drills'] = [Point(point)]

                # repopulate the 'solid_geometry' for each tool
                poly = Point(point).buffer(float(tool_dia[0]) / 2.0, int(int(exc_obj.geo_steps_per_circle) / 4))
                self.new_tools[current_tool]['solid_geometry'].append(poly)

        ordered_edited_slot_points = sorted(zip(edited_slot_points.keys(), edited_slot_points.values()))
        for tool_dia in ordered_edited_slot_points:

            tool_exist_flag = False
            for tool in self.new_tools:
                if tool_dia[0] == self.new_tools[tool]["tooldia"]:
                    current_tool = tool
                    tool_exist_flag = True
                    break

            if tool_exist_flag is False:
                current_tool += 1

                # create the self.tools for the new Excellon object (the one with edited content)
                if current_tool not in self.new_tools:
                    self.new_tools[current_tool] = {}
                self.new_tools[current_tool]['tooldia'] = float(tool_dia[0])

                # add in self.tools the 'solid_geometry' key, the value (a list) is populated below
                self.new_tools[current_tool]['solid_geometry'] = []

            # create the self.slots for the new Excellon object (the one with edited content)
            for coord_dict in tool_dia[1]:
                slot = (
                    Point(coord_dict['start']),
                    Point(coord_dict['stop'])
                )
                try:
                    self.new_tools[current_tool]['slots'].append(slot)
                except KeyError:
                    self.new_tools[current_tool]['slots'] = [slot]

                # repopulate the 'solid_geometry' for each tool
                poly = LineString([coord_dict['start'], coord_dict['stop']]).buffer(
                    float(tool_dia[0]) / 2.0, int(int(exc_obj.geo_steps_per_circle) / 4)
                )
                self.new_tools[current_tool]['solid_geometry'].append(poly)

        if self.is_modified is True:
            if "_edit" in self.edited_obj_name:
                try:
                    idd = int(self.edited_obj_name[-1]) + 1
                    self.edited_obj_name = self.edited_obj_name[:-1] + str(idd)
                except ValueError:
                    self.edited_obj_name += "_1"
            else:
                self.edited_obj_name += "_edit"

        self.app.worker_task.emit({'fcn': self.new_edited_excellon,
                                   'params': [self.edited_obj_name, self.new_tools]})

        return self.edited_obj_name

    @staticmethod
    def update_options(obj):
        try:
            if not obj.obj_options:
                obj.obj_options = {'xmin': 0, 'ymin': 0, 'xmax': 0, 'ymax': 0}
                return True
            else:
                return False
        except AttributeError:
            obj.obj_options = {}
            return True

    def new_edited_excellon(self, outname,  n_tools):
        """
        Creates a new Excellon object for the edited Excellon. Thread-safe.

        :param outname:     Name of the resulting object. None causes the
                            name to be that of the file.
        :type outname:      str

        :param n_tools:     The new Tools storage
        :return:            None
        """

        self.app.log.debug("Update the Excellon object with edited content. Source is %s" %
                           self.edited_obj.obj_options['name'])

        new_tools = n_tools

        # How the object should be initialized
        def obj_init(new_obj, app_obj):
            new_obj.tools = deepcopy(new_tools)

            new_obj.obj_options['name'] = outname

            # add a 'data' dict for each tool with the default values
            for tool in new_obj.tools:
                new_obj.tools[tool]['data'] = {}
                new_obj.tools[tool]['data'].update(deepcopy(self.data_defaults))

            try:
                new_obj.create_geometry()
            except KeyError:
                self.app.inform.emit('[ERROR_NOTCL] %s' %
                                     _("There are no Tools definitions in the file. Aborting Excellon creation.")
                                     )
            except Exception:
                msg = '[ERROR] %s' % \
                      _("An internal error has occurred. See shell.\n")
                msg += traceback.format_exc()
                app_obj.inform.emit(msg)
                return

        with self.app.proc_container.new('%s...' % _("Generating")):

            try:
                edited_obj = self.app.app_obj.new_object("excellon", outname, obj_init)
                edited_obj.source_file = self.app.f_handlers.export_excellon(obj_name=edited_obj.obj_options['name'],
                                                                             local_use=edited_obj,
                                                                             filename=None,
                                                                             use_thread=False)
            except Exception as e:
                self.deactivate()

                # make sure that we do not carry the reference of the edited object further along
                self.edited_obj = None

                self.app.log.error("Error on Edited object creation: %s" % str(e))
                return

            self.deactivate()

            # make sure that we do not carry the reference of the edited object further along
            self.edited_obj = None

            self.app.inform.emit('[success] %s' % _("Excellon editing finished."))

    def on_tool_select(self, tool):
        """
        Behavior of the toolbar. Tool initialization.

        :rtype : None
        """
        current_tool = tool

        self.app.log.debug("on_tool_select('%s')" % tool)

        if self.last_tool_selected is None and current_tool != 'drill_select':
            # self.draw_app.select_tool('drill_select')
            self.complete = True
            current_tool = 'drill_select'
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled. There is no Tool/Drill selected"))

        # This is to make the group behave as radio group
        if current_tool in self.tools_exc:
            if self.tools_exc[current_tool]["button"].isChecked():
                self.app.log.debug("%s is checked." % current_tool)
                for t in self.tools_exc:
                    if t != current_tool:
                        self.tools_exc[t]["button"].setChecked(False)

                # this is where the Editor toolbar classes (button's) are instantiated
                self.active_tool = self.tools_exc[current_tool]["constructor"](self)
                # self.app.inform.emit(self.active_tool.start_msg)
            else:
                self.app.log.debug("%s is NOT checked." % current_tool)
                for t in self.tools_exc:
                    self.tools_exc[t]["button"].setChecked(False)

                self.select_tool('drill_select')
                self.active_tool = SelectEditorExc(self)

    def on_row_selected(self, row, col):
        key_modifier = QtWidgets.QApplication.keyboardModifiers()
        if self.app.options["global_mselect_key"] == 'Control':
            modifier_to_use = Qt.KeyboardModifier.ControlModifier
        else:
            modifier_to_use = Qt.KeyboardModifier.ShiftModifier

        if key_modifier == modifier_to_use:
            pass
        else:
            self.selected.clear()

        try:
            self.last_tool_selected = int(row) + 1

            selected_dia = self.tool2tooldia[self.last_tool_selected]
            for obj in self.storage_dict[selected_dia].get_objects():
                self.selected.append(obj)
        except Exception as e:
            self.app.log.error(str(e))

        self.replot()

    def on_table_selection(self):
        selected_rows = self.ui.tools_table_exc.selectionModel().selectedRows(0)

        if len(selected_rows) == self.ui.tools_table_exc.rowCount():
            for row in range(self.ui.tools_table_exc.rowCount() - 2):   # last 2 columns have no diameter
                sel_dia = self.app.dec_format(float(self.ui.tools_table_exc.item(row, 1).text()), self.app.decimals)
                for obj in self.storage_dict[sel_dia].get_objects():
                    self.selected.append(obj)
            self.replot()
            return True
        return False

    def on_canvas_click(self, event):
        """
        event.x and .y have canvas coordinates
        event.xdata and .ydata have plot coordinates

        :param event:       Event object dispatched by VisPy
        :return:            None
        """
        if self.app.use_3d_engine:
            event_pos = event.pos
            # event_is_dragging = event.is_dragging
            # right_button = 2
        else:
            event_pos = (event.xdata, event.ydata)
            # event_is_dragging = self.app.plotcanvas.is_dragging
            # right_button = 3

        if event.button == 1:
            self.clicked_pos = self.canvas.translate_coords(event_pos)
            if self.app.grid_status():
                self.clicked_pos = self.app.geo_editor.snap(self.clicked_pos[0], self.clicked_pos[1])
            else:
                self.clicked_pos = (self.clicked_pos[0], self.clicked_pos[1])

            self.on_canvas_click_left_handler()

    def on_canvas_click_left_handler(self, custom_pos=None):
        self.app.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
                                               "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (0, 0))

        click_position = custom_pos if custom_pos is not None else self.clicked_pos
        if self.active_tool is not None:
            # Dispatch event to active_tool
            self.active_tool.click(click_position)

            # If it is a shape generating tool
            if isinstance(self.active_tool, FCShapeTool) and self.active_tool.complete:
                if self.current_storage is not None:
                    self.on_exc_shape_complete(self.current_storage)
                    self.build_ui()

                # MS: always return to the Select Tool if modifier key is not pressed
                # else return to the current tool
                if self.app.options["global_mselect_key"] == 'Control':
                    modifier_to_use = Qt.KeyboardModifier.ControlModifier
                else:
                    modifier_to_use = Qt.KeyboardModifier.ShiftModifier

                # if modifier key is pressed then we add to the selected list the current shape but if it's already
                # in the selected list, we removed it. Therefore, first click selects, second deselects.
                if QtWidgets.QApplication.keyboardModifiers() == modifier_to_use:
                    self.select_tool(self.active_tool.name)
                else:
                    # return to Select tool but not for FCDrillAdd or SlotAdd
                    if isinstance(self.active_tool, DrillAdd) or isinstance(self.active_tool, SlotAdd):
                        self.select_tool(self.active_tool.name)
                    else:
                        self.select_tool("drill_select")
                    return

            if isinstance(self.active_tool, SelectEditorExc):
                # self.app.log.debug("Replotting after click.")
                self.replot()
        else:
            self.app.log.debug("No active tool to respond to click!")

    def on_exc_click_release(self, event):
        """
        Handler of the "mouse_release" event.
        It will pop-up the context menu on right mouse click unless there was a panning move (decided in the
        "mouse_move" event handler) and only if the current tool is the Select tool.
        It will 'close' a Editor tool if it is the case.

        :param event:       Event object dispatched by VisPy SceneCavas
        :return:            None
        """

        if self.app.use_3d_engine:
            event_pos = event.pos
            # event_is_dragging = event.is_dragging
            right_button = 2
        else:
            event_pos = (event.xdata, event.ydata)
            # event_is_dragging = self.app.plotcanvas.is_dragging
            right_button = 3

        pos_canvas = self.canvas.translate_coords(event_pos)

        if self.app.grid_status():
            pos = self.app.geo_editor.snap(pos_canvas[0], pos_canvas[1])
        else:
            pos = (pos_canvas[0], pos_canvas[1])

        # if the released mouse button was RMB then test if it was a panning motion or not, if not it was a context
        # canvas menu
        try:
            if event.button == right_button:  # right click
                if self.app.ui.popMenu.mouse_is_panning is False:
                    try:
                        QtGui.QGuiApplication.restoreOverrideCursor()
                    except Exception:
                        pass
                    if self.active_tool.complete is False and not isinstance(self.active_tool, SelectEditorExc):
                        self.active_tool.complete = True
                        self.in_action = False
                        self.delete_utility_geometry()
                        self.app.inform.emit('[success] %s' % _("Done."))
                        self.select_tool('drill_select')
                    else:
                        if isinstance(self.active_tool, DrillAdd):
                            self.active_tool.complete = True
                            self.in_action = False
                            self.delete_utility_geometry()
                            self.app.inform.emit('[success] %s' % _("Done."))
                            self.select_tool('drill_select')

                        self.app.cursor = QtGui.QCursor()
                        self.app.populate_cmenu_grids()
                        self.app.ui.popMenu.popup(self.app.cursor.pos())

        except Exception as e:
            self.app.log.error("AppExcEditor.on_exc_click_release() RMB click --> Error: %s" % str(e))
            raise

        # if the released mouse button was LMB then test if we had a right-to-left selection or a left-to-right
        # selection and then select a type of selection ("enclosing" or "touching")
        if event.button == 1:  # left click
            if self.app.selection_type is not None:
                try:
                    self.draw_selection_area_handler(self.clicked_pos, pos, self.app.selection_type)
                except Exception as e:
                    self.app.log.error("AppExcEditor.on_exc_click_release() LMB click --> Error: %s" % str(e))
                    raise
                self.app.selection_type = None
            elif isinstance(self.active_tool, SelectEditorExc):
                self.active_tool.click_release((self.clicked_pos[0], self.clicked_pos[1]))

                # if there are selected objects then plot them
                if self.selected:
                    self.replot()

            click_position = pos if pos is not None else self.clicked_pos
            if self.active_tool is not None and self.active_tool.name != 'drill_select':
                # Dispatch event to active_tool
                try:
                    self.active_tool.click_release(click_position)
                except AttributeError:
                    pass

    def on_canvas_move(self, event):
        """
        Called on 'mouse_move' event.
        It updates the mouse cursor if the grid snapping is ON.
        It decides if we have a mouse drag and if it is done with the right mouse click. Then it passes this info to a
        class object which is used in the "mouse_release" handler to decide if to pop-up the context menu or not.
        It draws utility_geometry for the Editor tools.
        Update the position labels from status bar.
        Decide if we have a right to left or a left to right mouse drag with left mouse button and call a function
        that will draw a selection shape on canvas.

        event.pos have canvas screen coordinates

        :param event:       Event object dispatched by VisPy SceneCavas
        :return:            None
        """

        if not self.app.plotcanvas.native.hasFocus():
            self.app.plotcanvas.native.setFocus()

        if self.app.use_3d_engine:
            event_pos = event.pos
            event_is_dragging = event.is_dragging
            right_button = 2
        else:
            event_pos = (event.xdata, event.ydata)
            event_is_dragging = self.app.plotcanvas.is_dragging
            right_button = 3

        pos = self.canvas.translate_coords(event_pos)
        event.xdata, event.ydata = pos[0], pos[1]

        self.x = event.xdata
        self.y = event.ydata

        self.app.ui.popMenu.mouse_is_panning = False

        # if the RMB is clicked and mouse is moving over plot then 'panning_action' is True
        if event.button == right_button and event_is_dragging == 1:
            self.app.ui.popMenu.mouse_is_panning = True
            return

        try:
            x = float(event.xdata)
            y = float(event.ydata)
        except TypeError:
            return

        if self.active_tool is None:
            return

        # ## Snap coordinates
        if self.app.grid_status():
            x, y = self.app.geo_editor.snap(x, y)

            # Update cursor
            self.app.app_cursor.set_data(np.asarray([(x, y)]), symbol='++', edge_color=self.app.plotcanvas.cursor_color,
                                         edge_width=self.app.options["global_cursor_width"],
                                         size=self.app.options["global_cursor_size"])

        self.snap_x = deepcopy(x)
        self.snap_y = deepcopy(y)

        if self.clicked_pos is None:
            self.clicked_pos = (0, 0)
        self.app.dx = x - self.clicked_pos[0]
        self.app.dy = y - self.clicked_pos[1]

        # # update the position label in the infobar since the APP mouse event handlers are disconnected
        # self.app.ui.position_label.setText("&nbsp;<b>X</b>: %.4f&nbsp;&nbsp;   "
        #                                    "<b>Y</b>: %.4f&nbsp;" % (x, y))
        # # # update the reference position label in the infobar since the APP mouse event handlers are disconnected
        # self.app.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
        #                                        "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (self.app.dx, self.app.dy))
        self.app.ui.update_location_labels(self.app.dx, self.app.dy, x, y)

        # units = self.app.app_units.lower()
        # self.app.plotcanvas.text_hud.text = \
        #     'Dx:\t{:<.4f} [{:s}]\nDy:\t{:<.4f} [{:s}]\n\nX:  \t{:<.4f} [{:s}]\nY:  \t{:<.4f} [{:s}]'.format(
        #         self.app.dx, units, self.app.dy, units, x, units, y, units)
        self.app.plotcanvas.on_update_text_hud(self.app.dx, self.app.dy, x, y)

        # ## Utility geometry (animated)
        # self.update_utility_geometry(data=(x, y))

        self.update_utility_geometry(data=(x, y))
        if self.active_tool.name in [
            'drill_add', 'drill_array', 'slot_add', 'slot_array', 'drill_copy', 'drill_resize', 'drill_move'
        ]:
            try:
                self.active_tool.draw_cursor_data(pos=(x, y))
            except AttributeError:
                # this can happen if the method is not implemented yet for the active_tool
                pass

        # ## Selection area on canvas section # ##
        if event_is_dragging == 1 and event.button == 1:
            # I make an exception for FCDrillAdd and DrillArray because clicking and dragging while making regions
            # can create strange issues. Also for SlotAdd and SlotArray
            if isinstance(self.active_tool, DrillAdd) or isinstance(self.active_tool, DrillArray) or \
                    isinstance(self.active_tool, SlotAdd) or isinstance(self.active_tool, SlotArray):
                self.app.selection_type = None
            else:
                dx = pos[0] - self.clicked_pos[0]
                self.app.delete_selection_shape()
                if dx < 0:
                    self.app.draw_moving_selection_shape((self.clicked_pos[0], self.clicked_pos[1]), (x, y),
                                                         color=self.app.options["global_alt_sel_line"],
                                                         face_color=self.app.options['global_alt_sel_fill'])
                    self.app.selection_type = False
                else:
                    self.app.draw_moving_selection_shape((self.clicked_pos[0], self.clicked_pos[1]), (x, y))
                    self.app.selection_type = True
        else:
            self.app.selection_type = None

        # Update cursor
        self.app.app_cursor.set_data(np.asarray([(x, y)]), symbol='++', edge_color=self.app.plotcanvas.cursor_color,
                                     edge_width=self.app.options["global_cursor_width"],
                                     size=self.app.options["global_cursor_size"])

    def add_exc_shape(self, shp, storage):
        """
        Adds a shape to a specified shape storage.

        :param shp:       Shape to be added.
        :type shp:        DrawToolShape
        :param storage:     object where to store the shapes
        :return:            None
        """
        # List of DrawToolShape?
        if isinstance(shp, list):
            for subshape in shp:
                self.add_exc_shape(subshape, storage)
            return

        assert isinstance(shp, DrawToolShape), \
            "Expected a DrawToolShape, got %s" % str(type(shp))

        assert shp.geo is not None, \
            "Shape object has empty geometry (None)"

        assert (isinstance(shp.geo, list) and len(shp.geo) > 0) or not isinstance(shp.geo, list), \
            "Shape objects has empty geometry ([])"

        if isinstance(shp, DrawToolUtilityShape):
            self.utility.append(shp)
        else:
            storage.insert(shp)  # TODO: Check performance

    def add_shape(self, shp):
        """
        Adds a shape to the shape storage.

        :param shp: Shape to be added.
        :type shp:  DrawToolShape
        :return:    None
        """

        # List of DrawToolShape?
        if isinstance(shp, list):
            for subshape in shp:
                self.add_shape(subshape)
            return

        assert isinstance(shp, DrawToolShape), \
            "Expected a DrawToolShape, got %s" % type(shp)

        assert shp.geo is not None, \
            "Shape object has empty geometry (None)"

        assert (isinstance(shp.geo, list) and len(shp.geo) > 0) or not isinstance(shp.geo, list), \
            "Shape objects has empty geometry ([])"

        if isinstance(shp, DrawToolUtilityShape):
            self.utility.append(shp)
        # else:
        #     self.storage.insert(shape)

    def on_exc_shape_complete(self, storage):
        self.app.log.debug("on_shape_complete()")

        # Add shape
        if type(storage) is list:
            for item_storage in storage:
                self.add_exc_shape(self.active_tool.geometry, item_storage)
        else:
            self.add_exc_shape(self.active_tool.geometry, storage)

        # Remove any utility shapes
        self.delete_utility_geometry()
        self.tool_shape.clear(update=True)

        # Replot and reset tool.
        self.replot()
        # self.active_tool = type(self.active_tool)(self)

    def draw_selection_area_handler(self, start, end, sel_type):
        """
        This function is called whenever we have a left mouse click release and only we have a left mouse click drag,
        be it from left to right or from right to left. The direction of the drag is decided in the "mouse_move"
        event handler.
        Pressing a modifier key (eg. Ctrl, Shift or Alt) will change the behavior of the selection.

        Depending on which tool belongs the selected shapes, the corresponding rows in the Tools Table are selected or
        deselected.

        :param start:       mouse position when the selection LMB click was done
        :param end:         mouse position when the left mouse button is released
        :param sel_type:    if True it's a left to right selection (enclosure), if False it's a 'touch' selection
        :return:
        """

        start_pos = (start[0], start[1])
        end_pos = (end[0], end[1])
        poly_selection = Polygon([start_pos, (end_pos[0], start_pos[1]), end_pos, (start_pos[0], end_pos[1])])
        modifiers = None

        # delete the selection shape that was just drawn, we no longer need it
        self.app.delete_selection_shape()

        # detect if a modifier key was pressed while the left mouse button was released
        self.modifiers = QtWidgets.QApplication.keyboardModifiers()
        if self.modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier:
            modifiers = 'Shift'
        elif self.modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            modifiers = 'Control'

        if modifiers == self.app.options["global_mselect_key"]:
            for storage in self.storage_dict:
                for obj in self.storage_dict[storage].get_objects():
                    if (sel_type is True and poly_selection.contains(obj.geo)) or \
                            (sel_type is False and poly_selection.intersects(obj.geo)):

                        if obj in self.selected:
                            # remove the shape object from the selected shapes storage
                            self.selected.remove(obj)
                        else:
                            # add the shape object to the selected shapes storage
                            self.selected.append(obj)
        else:
            # clear the selection shapes storage
            self.selected.clear()
            # then add to the selection shapes storage the shapes that are included (touched) by the selection rectangle
            for storage in self.storage_dict:
                for obj in self.storage_dict[storage].get_objects():
                    if (sel_type is True and poly_selection.contains(obj.geo)) or \
                            (sel_type is False and poly_selection.intersects(obj.geo)):
                        self.selected.append(obj)

        try:
            self.ui.tools_table_exc.cellPressed.disconnect()
        except Exception:
            pass

        # first deselect all rows (tools) in the Tools Table
        self.ui.tools_table_exc.clearSelection()
        # and select the rows (tools) in the tool table according to the diameter(s) of the selected shape(s)
        self.ui.tools_table_exc.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        for storage in self.storage_dict:
            for shape_s in self.selected:
                if shape_s in self.storage_dict[storage].get_objects():
                    for key_tool_nr in self.tool2tooldia:
                        if self.tool2tooldia[key_tool_nr] == storage:
                            row_to_sel = key_tool_nr - 1
                            # item = self.ui.tools_table_exc.item(row_to_sel, 1)
                            # self.ui.tools_table_exc.setCurrentItem(item)
                            # item.setSelected(True)

                            # if the row to be selected is not already in the selected rows then select it
                            # otherwise don't do it as it seems that we have a toggle effect
                            if row_to_sel not in set(
                                    index.row() for index in self.ui.tools_table_exc.selectedIndexes()):
                                self.ui.tools_table_exc.selectRow(row_to_sel)
                            self.last_tool_selected = int(key_tool_nr)

        self.ui.tools_table_exc.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)

        self.ui.tools_table_exc.cellPressed.connect(self.on_row_selected)
        self.replot()

    def update_utility_geometry(self, data):
        # ### Utility geometry (animated) ###
        geo = self.active_tool.utility_geometry(data=data)
        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            # Remove any previous utility shape
            self.tool_shape.clear(update=True)
            self.draw_utility_geometry(geo=geo)

    # def on_canvas_key_release(self, event):
    #     self.key = None

    def draw_utility_geometry(self, geo):
        # Add the new utility shape

        if isinstance(geo.geo, (MultiLineString, MultiPolygon)):
            util_geo = geo.geo.geoms
        else:
            util_geo = geo.geo

        try:
            # this case is for the Font Parse
            for el in util_geo:
                if isinstance(el, (MultiLineString, MultiPolygon)):
                    for sub_geo in el.geoms:
                        self.tool_shape.add(
                            shape=sub_geo,
                            color=self.get_draw_color(),
                            update=False,
                            layer=0,
                            tolerance=None
                        )
                else:
                    self.tool_shape.add(
                        shape=el,
                        color=self.get_draw_color(),
                        update=False,
                        layer=0,
                        tolerance=None)
        except TypeError:
            self.tool_shape.add(
                shape=util_geo,
                color=self.get_draw_color(),
                update=False,
                layer=0,
                tolerance=None)
        # print(self.tool_shape.data)
        self.tool_shape.redraw()

    def get_draw_color(self):
        orig_color = self.app.options["global_draw_color"]

        if self.app.options['global_theme'] in ['default', 'light']:
            return orig_color

        # in the "dark" theme we invert the color
        lowered_color = orig_color.lower()
        group1 = "#0123456789abcdef"
        group2 = "#fedcba9876543210"
        # create color dict
        color_dict = {group1[i]: group2[i] for i in range(len(group1))}
        new_color = ''.join([color_dict[j] for j in lowered_color])
        return new_color

    def get_sel_color(self):
        return self.app.options['global_sel_draw_color']

    def replot(self):
        self.plot_all()

    def plot_all(self):
        """
        Plots all shapes in the editor.

        :return:    None
        :rtype:     None
        """

        self.shapes.clear(update=True)

        for storage in self.storage_dict:
            for shape_plus in self.storage_dict[storage].get_objects():
                if shape_plus.geo is None:
                    continue

                if shape_plus in self.selected:
                    self.plot_shape(geometry=shape_plus.geo,
                                    color=self.get_sel_color()[:-2] + 'FF',
                                    linewidth=2)
                    continue
                self.plot_shape(geometry=shape_plus.geo, color=self.get_draw_color()[:-2] + 'FF')

        for shape_form in self.utility:
            self.plot_shape(geometry=shape_form.geo, linewidth=1)
            continue

        self.shapes.redraw()

    def plot_shape(self, geometry=None, color='0x000000FF', linewidth=1):
        """
        Plots a geometric object or list of objects without rendering. Plotted objects
        are returned as a list. This allows for efficient/animated rendering.

        :param geometry:    Geometry to be plotted (Any Shapely.geom kind or list of such)
        :param color:       Shape color
        :param linewidth:   Width of lines in # of pixels.
        :return:            List of plotted elements.
        """
        plot_elements = []

        if geometry is None:
            geometry = self.active_tool.geometry

        if isinstance(geometry, (MultiLineString, MultiPolygon)):
            use_geometry = geometry.geoms
        else:
            use_geometry = geometry

        try:
            for geo in use_geometry:
                plot_elements += self.plot_shape(geometry=geo, color=color, linewidth=linewidth)

        # ## Non-iterable
        except TypeError:
            # ## DrawToolShape
            if isinstance(use_geometry, DrawToolShape):
                plot_elements += self.plot_shape(geometry=use_geometry.geo, color=color, linewidth=linewidth)

            # ## Polygon: Descend into exterior and each interior.
            if isinstance(use_geometry, Polygon):
                plot_elements += self.plot_shape(geometry=use_geometry.exterior, color=color, linewidth=linewidth)
                plot_elements += self.plot_shape(geometry=use_geometry.interiors, color=color, linewidth=linewidth)

            if isinstance(use_geometry, (LineString, LinearRing)):
                plot_elements.append(self.shapes.add(shape=use_geometry, color=color, layer=0,
                                                     tolerance=self.tolerance))

            if type(geometry) == Point:
                pass

        return plot_elements

    def on_shape_complete(self):
        # Add shape
        self.add_shape(self.active_tool.geometry)

        # Remove any utility shapes
        self.delete_utility_geometry()
        self.tool_shape.clear(update=True)

        # Replot and reset tool.
        self.replot()
        # self.active_tool = type(self.active_tool)(self)

    def get_selected(self):
        """
        Returns list of shapes that are selected in the editor.

        :return: List of shapes.
        """
        return self.selected

    def delete_selected(self):
        temp_ref = [s for s in self.selected]
        for shape_sel in temp_ref:
            self.delete_shape(shape_sel)

        self.selected.clear()
        self.build_ui()
        self.app.inform.emit('[success] %s' % _("Done."))

    def delete_shape(self, del_shape):
        self.is_modified = True

        if del_shape in self.utility:
            self.utility.remove(del_shape)
            return

        for storage in self.storage_dict:
            # try:
            #     self.storage_dict[storage].remove(shape)
            # except:
            #     pass
            if del_shape in self.storage_dict[storage].get_objects():
                if isinstance(del_shape.geo, MultiLineString):
                    self.storage_dict[storage].remove(del_shape)
                    # a hack to make the plugin_table display less drills per diameter
                    # self.points_edit it's only useful first time when we load the data into the storage
                    # but is still used as referecen when building plugin_table in self.build_ui()
                    # the number of drills displayed in column 2 is just a len(self.points_edit) therefore
                    # deleting self.points_edit elements (doesn't matter who but just the number)
                    # solved the display issue.
                    del self.points_edit[storage][0]
                else:
                    self.storage_dict[storage].remove(del_shape)
                    del self.slot_points_edit[storage][0]

        if del_shape in self.selected:
            self.selected.remove(del_shape)

    def delete_utility_geometry(self):
        for_deletion = [util_shape for util_shape in self.utility]
        for util_shape in for_deletion:
            self.delete_shape(util_shape)

        self.tool_shape.clear(update=True)
        self.tool_shape.redraw()

    def on_delete_btn(self):
        self.delete_selected()
        self.replot()

    def select_tool(self, pluginName):
        """
        Selects a drawing tool. Impacts the object and appGUI.

        :param pluginName:    Name of the tool.
        :return:            None
        """
        self.tools_exc[pluginName]["button"].setChecked(True)
        self.on_tool_select(pluginName)

    def set_selected(self, sel_shape):

        # Remove and add to the end.
        if sel_shape in self.selected:
            self.selected.remove(sel_shape)

        self.selected.append(sel_shape)

    def set_unselected(self, unsel_shape):
        if unsel_shape in self.selected:
            self.selected.remove(unsel_shape)

    def exc_add_drill(self):
        self.select_tool('drill_add')
        return

    def exc_add_drill_array(self):
        self.select_tool('drill_array')
        return

    def exc_add_slot(self):
        self.select_tool('slot_add')
        return

    def exc_add_slot_array(self):
        self.select_tool('slot_array')
        return

    def exc_resize_drills(self):
        self.select_tool('drill_resize')
        return

    def exc_copy_drills(self):
        self.select_tool('drill_copy')
        return

    def exc_move_drills(self):
        self.select_tool('drill_move')
        return

    def on_slots_conversion(self):
        # selected rows
        selected_rows = set()
        for it in self.ui.tools_table_exc.selectedItems():
            selected_rows.add(it.row())

        # convert a Polygon (slot) to a MultiLineString (drill)
        def convert_slot2drill(geo_elem, tool_dia):
            point = geo_elem.centroid
            start_hor_line = ((point.x - (tool_dia / 2)), point.y)
            stop_hor_line = ((point.x + (tool_dia / 2)), point.y)
            start_vert_line = (point.x, (point.y - (tool_dia / 2)))
            stop_vert_line = (point.x, (point.y + (tool_dia / 2)))
            return MultiLineString([(start_hor_line, stop_hor_line), (start_vert_line, stop_vert_line)])

        # temporary new storage: a dist with keys the tool diameter and values Rtree storage
        new_storage_dict = {}

        for row in selected_rows:
            table_tooldia = self.dec_format(float(self.ui.tools_table_exc.item(row, 1).text()))
            for dict_dia, geo_dict in self.storage_dict.items():
                if self.dec_format(float(dict_dia)) == table_tooldia:
                    storage_elem = AppGeoEditor.make_storage()
                    for shp in geo_dict.get_objects():
                        if isinstance(shp.geo, MultiLineString):
                            # it's a drill just add it as it is to storage
                            self.add_exc_shape(shp, storage_elem)
                        if isinstance(shp.geo, Polygon):
                            # it's a slot, convert drill to slot and then add it to storage
                            new_shape = convert_slot2drill(shp.geo, table_tooldia)
                            self.add_exc_shape(DrawToolShape(new_shape), storage_elem)

                    new_storage_dict[table_tooldia] = storage_elem

        self.storage_dict.update(new_storage_dict)
        self.replot()


class AppExcEditorUI:
    def __init__(self, app):
        self.app = app

        # Number of decimals used by tools in this class
        self.decimals = self.app.decimals

        # ## Current application units in Upper Case
        self.units = self.app.app_units.upper()

        self.exc_edit_widget = QtWidgets.QWidget()
        # ## Box for custom widgets
        # This gets populated in offspring implementations.
        layout = QtWidgets.QVBoxLayout()
        self.exc_edit_widget.setLayout(layout)

        # add a frame and inside add a vertical box layout. Inside this vbox layout I add all the Drills widgets
        # this way I can hide/show the frame
        self.drills_frame = QtWidgets.QFrame()
        self.drills_frame.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.drills_frame)

        # #############################################################################################################
        # ######################## MAIN Grid ##########################################################################
        # #############################################################################################################
        self.ui_vertical_lay = QtWidgets.QVBoxLayout()
        self.ui_vertical_lay.setContentsMargins(0, 0, 0, 0)
        self.drills_frame.setLayout(self.ui_vertical_lay)

        # Page Title box (spacing between children)
        self.title_box = QtWidgets.QHBoxLayout()
        self.ui_vertical_lay.addLayout(self.title_box)

        # Page Title
        pixmap = QtGui.QPixmap(self.app.resource_location + '/app32.png')
        self.icon = FCLabel()
        self.icon.setPixmap(pixmap)

        self.title_label = FCLabel("<font size=5><b>%s</b></font>" % _('Excellon Editor'))
        self.title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

        self.title_box.addWidget(self.icon, stretch=0)
        self.title_box.addWidget(self.title_label, stretch=1)

        # App Level label
        self.level = QtWidgets.QToolButton()
        self.level.setToolTip(
            _(
                "Beginner Mode - many parameters are hidden.\n"
                "Advanced Mode - full control.\n"
                "Permanent change is done in 'Preferences' menu."
            )
        )
        # self.level.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.level.setCheckable(True)
        self.title_box.addWidget(self.level)

        # Object name box
        self.name_box = QtWidgets.QHBoxLayout()
        self.ui_vertical_lay.addLayout(self.name_box)

        # Object Name
        name_label = FCLabel(_("Name:"))
        self.name_entry = FCEntry()

        self.name_box.addWidget(name_label)
        self.name_box.addWidget(self.name_entry)

        # Tools Drills Table Title
        self.tools_table_label = FCLabel('%s' % _('Tools Table'), bold=True)
        self.tools_table_label.setToolTip(
            _("Tools in this Excellon object\n"
              "when are used for drilling.")
        )
        self.ui_vertical_lay.addWidget(self.tools_table_label)

        # #############################################################################################################
        # ########################################## Drills TABLE #####################################################
        # #############################################################################################################
        self.tools_table_exc = FCTable()
        self.tools_table_exc.setColumnCount(4)
        self.tools_table_exc.setHorizontalHeaderLabels(['#', _('Diameter'), 'D', 'S'])
        self.tools_table_exc.setSortingEnabled(False)
        self.tools_table_exc.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)

        self.ui_vertical_lay.addWidget(self.tools_table_exc)

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        self.ui_vertical_lay.addWidget(separator_line)

        self.convert_slots_btn = FCButton('%s' % _("Convert Slots"))
        self.convert_slots_btn.setIcon(QtGui.QIcon(self.app.resource_location + '/convert32.png'))

        self.convert_slots_btn.setToolTip(
            _("Convert the slots in the selected tools to drills.")
        )
        self.ui_vertical_lay.addWidget(self.convert_slots_btn)

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        self.ui_vertical_lay.addWidget(separator_line)

        # Add a new Tool
        self.addtool_label = FCLabel('%s' % _('Add/Delete Tool'), bold=True)
        self.addtool_label.setToolTip(
            _("Add/Delete a tool to the tool list\n"
              "for this Excellon object.")
        )
        self.ui_vertical_lay.addWidget(self.addtool_label)

        # #############################################################################################################
        # ######################## ADD New Tool Grid ##################################################################
        # #############################################################################################################
        grid1 = GLay(v_spacing=5, h_spacing=3)
        self.ui_vertical_lay.addLayout(grid1)

        # Tool Diameter Label
        addtool_entry_lbl = FCLabel('%s:' % _('Tool Dia'))
        addtool_entry_lbl.setToolTip(
            _("Diameter for the new tool")
        )

        hlay = QtWidgets.QHBoxLayout()
        # Tool Diameter Entry
        self.addtool_entry = FCDoubleSpinner(policy=False)
        self.addtool_entry.set_precision(self.decimals)
        self.addtool_entry.set_range(0.0000, 10000.0000)

        hlay.addWidget(self.addtool_entry)

        # Tool Diameter Button
        self.addtool_btn = FCButton(_('Add'))
        self.addtool_btn.setIcon(QtGui.QIcon(self.app.resource_location + '/plus16.png'))
        self.addtool_btn.setToolTip(
            _("Add a new tool to the tool list\n"
              "with the diameter specified above.")
        )
        hlay.addWidget(self.addtool_btn)

        grid1.addWidget(addtool_entry_lbl, 0, 0)
        grid1.addLayout(hlay, 0, 1)

        # Delete Tool
        self.deltool_btn = FCButton(_('Delete Tool'))
        self.deltool_btn.setIcon(QtGui.QIcon(self.app.resource_location + '/trash32.png'))
        self.deltool_btn.setToolTip(
            _("Delete a tool in the tool list\n"
              "by selecting a row in the tool table.")
        )
        grid1.addWidget(self.deltool_btn, 2, 0, 1, 2)

        # separator_line = QtWidgets.QFrame()
        # separator_line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        # separator_line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        # grid1.addWidget(separator_line, 4, 0, 1, 2)

        self.ui_vertical_lay.addStretch()
        layout.addStretch(1)

        # Editor
        self.exit_editor_button = FCButton(_('Exit Editor'), bold=True)
        self.exit_editor_button.setIcon(QtGui.QIcon(self.app.resource_location + '/power16.png'))
        self.exit_editor_button.setToolTip(
            _("Exit from Editor.")
        )
        layout.addWidget(self.exit_editor_button)

        # #############################################################################################################
        # ###################### INIT Excellon Editor UI ##############################################################
        # #############################################################################################################
        pass

        # ############################ FINSIHED GUI ###################################
        # #############################################################################

    def confirmation_message(self, accepted, minval, maxval):
        if accepted is False:
            self.app.inform[str, bool].emit('[WARNING_NOTCL] %s: [%.*f, %.*f]' % (_("Edited value is out of range"),
                                                                                  self.decimals,
                                                                                  minval,
                                                                                  self.decimals,
                                                                                  maxval), False)
        else:
            self.app.inform[str, bool].emit('[success] %s' % _("Edited value is within limits."), False)

    def confirmation_message_int(self, accepted, minval, maxval):
        if accepted is False:
            self.app.inform[str, bool].emit('[WARNING_NOTCL] %s: [%d, %d]' %
                                            (_("Edited value is out of range"), minval, maxval), False)
        else:
            self.app.inform[str, bool].emit('[success] %s' % _("Edited value is within limits."), False)


def get_shapely_list_bounds(geometry_list):
    xmin = np.Inf
    ymin = np.Inf
    xmax = -np.Inf
    ymax = -np.Inf

    for gs in geometry_list:
        try:
            gxmin, gymin, gxmax, gymax = gs.bounds
            xmin = min([xmin, gxmin])
            ymin = min([ymin, gymin])
            xmax = max([xmax, gxmax])
            ymax = max([ymax, gymax])
        except Exception as e:
            log.error("Tried to get bounds of empty geometry. --> %s" % str(e))

    return [xmin, ymin, xmax, ymax]

# EOF
